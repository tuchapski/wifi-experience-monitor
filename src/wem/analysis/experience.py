"""Explainable, versioned project heuristic; not an SLA or a root-cause classifier."""

import math
from dataclasses import dataclass

from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    ExperienceScore,
    ScoreComponent,
    ScoreMetric,
    WifiDeltaMetrics,
    WifiMetrics,
)

POLICY_VERSION = "experience-v1"
MINIMUM_COVERAGE = 70.0
COMPONENT_WEIGHTS = {"wifi": 30.0, "gateway": 20.0, "internet": 20.0, "dns": 15.0, "https": 15.0}


@dataclass(frozen=True)
class MetricRule:
    key: str
    label: str
    weight: float
    unit: str
    anchors: tuple[tuple[float, float], ...]
    minimum: float = 0.0
    maximum: float | None = None

    def describe(self) -> str:
        points = "; ".join(f"{value:g} {self.unit} → {score:g}" for value, score in self.anchors)
        return f"Linear interpolation: {points}. Outside anchors: nearest endpoint score."


# Metric weights are percentages WITHIN their component. All thresholds are
# initial project choices and must change together with POLICY_VERSION.
WIFI_RULES = (
    MetricRule("rssi", "RSSI", 40, "dBm", ((-90, 0), (-82, 40), (-75, 70), (-67, 100)), -127, -1),
    MetricRule(
        "retries",
        "TX retries",
        40,
        "/100 TX packets",
        ((0, 100), (10, 100), (20, 70), (50, 20), (100, 0)),
    ),
    MetricRule(
        "failures", "TX failures", 20, "/100 TX packets", ((0, 100), (1, 85), (5, 20), (10, 0))
    ),
)
LOSS_ANCHORS = ((0.0, 100.0), (1.0, 90.0), (5.0, 60.0), (20.0, 10.0), (100.0, 0.0))
CONNECTIVITY_RULES = {
    "gateway": (
        MetricRule(
            "latency",
            "Gateway latency",
            40,
            "ms",
            ((0, 100), (10, 100), (50, 70), (150, 20), (500, 0)),
        ),
        MetricRule("loss", "ICMP packet loss", 60, "%", LOSS_ANCHORS, 0, 100),
    ),
    "internet": (
        MetricRule(
            "latency",
            "External target latency",
            40,
            "ms",
            ((0, 100), (50, 100), (150, 70), (300, 20), (1000, 0)),
        ),
        MetricRule("loss", "ICMP packet loss", 60, "%", LOSS_ANCHORS, 0, 100),
    ),
    "dns": (
        MetricRule(
            "latency",
            "DNS resolution time",
            100,
            "ms",
            ((0, 100), (50, 100), (250, 70), (1000, 20), (3000, 0)),
        ),
    ),
    "https": (
        MetricRule(
            "latency",
            "HTTPS response time",
            100,
            "ms",
            ((0, 100), (300, 100), (1000, 70), (3000, 20), (5000, 0)),
        ),
    ),
}
COMPONENT_LABELS = {
    "wifi": "Wi-Fi",
    "gateway": "Gateway ICMP",
    "internet": "Internet target ICMP",
    "dns": "DNS",
    "https": "HTTPS",
}


def interpolate(value: float, rule: MetricRule) -> float:
    if value <= rule.anchors[0][0]:
        return rule.anchors[0][1]
    for (left, first), (right, last) in zip(rule.anchors, rule.anchors[1:], strict=False):
        if value <= right:
            return first + (last - first) * (value - left) / (right - left)
    return rule.anchors[-1][1]


def metric(
    rule: MetricRule,
    value: float | None,
    unavailable: str | None = None,
    failure: str | None = None,
) -> ScoreMetric:
    evidence = ScoreMetric(
        key=rule.key,
        label=rule.label,
        weight=rule.weight,
        unit=rule.unit,
        value=None,
        score=None,
        state="unavailable",
        reason="",
        rule=rule.describe(),
    )
    if unavailable:
        evidence.reason = unavailable
    elif failure:
        # Confirmed failure is evidence even if no latency or RSSI is possible.
        # Do not invent a numeric latency, loss percentage or signal reading.
        evidence.score = 0.0
        evidence.state = "failed"
        evidence.reason = failure
    elif (
        value is None
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < rule.minimum
        or (rule.maximum is not None and value > rule.maximum)
    ):
        evidence.reason = "Measurement missing, non-finite or outside its valid range."
    else:
        evidence.value = value
        evidence.score = round(interpolate(value, rule), 2)
        evidence.state = "measured"
        deduction = round(100 - evidence.score, 2)
        evidence.reason = f"Observed {value:g} {rule.unit}; metric deduction {deduction:g}/100."
    return evidence


def component(key: str, metrics: list[ScoreMetric], scope: str) -> ScoreComponent:
    covered = sum(item.weight for item in metrics if item.score is not None)
    score = (
        sum(item.weight * item.score for item in metrics if item.score is not None) / covered
        if covered
        else None
    )
    weight = COMPONENT_WEIGHTS[key]
    return ScoreComponent(
        key=key,
        label=COMPONENT_LABELS[key],
        weight=weight,
        coverage_percent=covered,
        score=round(score, 2) if score is not None else None,
        scope=scope,
        metrics=metrics,
        available_weight=weight * covered / 100,
    )


class ExperienceScoreEngine:
    def calculate(
        self,
        wifi: WifiMetrics,
        wifi_delta: WifiDeltaMetrics | None,
        connectivity: ConnectivityMetrics,
        calibration: CalibrationResult | None,
        collector_errors: list[str] | None = None,
    ) -> ExperienceScore:
        parts = [self._wifi(wifi, wifi_delta)]
        for key in CONNECTIVITY_RULES:
            parts.append(self._connectivity(key, connectivity))
        coverage = sum(part.available_weight for part in parts)
        reasons = []
        enough = (
            coverage >= MINIMUM_COVERAGE
            and parts[0].score is not None
            and sum(part.score is not None for part in parts[1:]) >= 2
        )
        if not enough:
            reasons.append(
                f"Global score requires at least {MINIMUM_COVERAGE:g}% weighted coverage, "
                "usable Wi-Fi evidence "
                "and at least two connectivity components."
            )
        if coverage < 100:
            reasons.append(
                "Missing evidence is excluded, not scored zero. Available weights are "
                "renormalized; partial scores are not directly comparable to complete scores."
            )
        calibrated = calibration is not None and calibration.calibrated
        if not calibrated:
            reasons.append("Sensor calibration is incomplete; local causes remain unverified.")
        if collector_errors:
            reasons.append("Collection errors exist; valid evidence is shown with reservations.")
        value = None
        if coverage:
            total = 0.0
            for part in parts:
                part.effective_weight = round(100 * part.available_weight / coverage, 4)
                if enough and part.score is not None:
                    points = part.available_weight * part.score / coverage
                    total += points
                    part.contribution = round(points, 2)
                    part.deduction = round(part.available_weight * (100 - part.score) / coverage, 2)
            if enough:
                value = round(total, 1)
        status = (
            "unavailable"
            if not enough
            else (
                "complete" if coverage == 100 and calibrated and not collector_errors else "partial"
            )
        )
        reasons.append(
            "Project heuristic for configured tests, not proof of root cause or an SLA. "
            "An ICMP failure alone does not establish an Internet outage. "
            "DNS/HTTPS may use the host route. Optional RF survey data is not scored."
        )
        return ExperienceScore(
            policy_version=POLICY_VERSION,
            value=value,
            status=status,
            coverage_percent=round(coverage, 2),
            minimum_coverage_percent=MINIMUM_COVERAGE,
            components=parts,
            reasons=reasons,
        )

    @staticmethod
    def _wifi(wifi: WifiMetrics, delta: WifiDeltaMetrics | None) -> ScoreComponent:
        if wifi.associated is False:
            return component(
                "wifi",
                [
                    metric(rule, None, failure="Confirmed: Wi-Fi is not associated with an AP.")
                    for rule in WIFI_RULES
                ],
                "selected_interface",
            )
        unknown = None if wifi.associated is True else "Wi-Fi association is unverified."
        delta_reason = unknown
        if delta_reason is None and (
            delta is None
            or delta.unavailable_reason
            or delta.association_changed
            or delta.counter_reset_detected
            or delta.interval_seconds is None
            or not math.isfinite(delta.interval_seconds)
            or delta.interval_seconds <= 0
            or delta.tx_packets_delta is None
            or delta.tx_packets_delta <= 0
        ):
            delta_reason = (
                delta.unavailable_reason
                if delta and delta.unavailable_reason
                else "No comparable TX interval; counters may be missing, reset or idle."
            )
        return component(
            "wifi",
            [
                metric(WIFI_RULES[0], wifi.signal_dbm, unknown),
                metric(
                    WIFI_RULES[1], delta.tx_retries_per_100_packets if delta else None, delta_reason
                ),
                metric(WIFI_RULES[2], delta.tx_failed_percent if delta else None, delta_reason),
            ],
            "selected_interface",
        )

    @staticmethod
    def _connectivity(key: str, data: ConnectivityMetrics) -> ScoreComponent:
        rules = CONNECTIVITY_RULES[key]
        outcome = data.tests.get(key)
        values: tuple[float | None, ...]
        if key in {"gateway", "internet"}:
            success = getattr(data, f"{key}_reachable")
            values = (
                getattr(data, f"{key}_latency_avg_ms"),
                getattr(data, f"{key}_packet_loss_percent"),
            )
        else:
            success = getattr(data, f"{key}_success")
            values = (data.dns_latency_ms if key == "dns" else data.https_total_time_ms,)
        unavailable, failure = None, None
        if outcome is None:
            unavailable = "No explicit test outcome; legacy measurements are not assumed valid."
        elif outcome.status not in {"passed", "failed"}:
            unavailable = f"{outcome.status}: {outcome.reason}"
        elif success is None or (outcome.status == "passed") != success:
            unavailable = "Test outcome and success flag are inconsistent or incomplete."
        elif outcome.status == "failed":
            failure = f"Confirmed test failure: {outcome.reason}"
            if key in {"gateway", "internet"}:
                failure += " ICMP failure is not proof of a general network outage."
        scope = (
            outcome.scope
            if outcome
            else ("host" if key in {"dns", "https"} else "selected_interface")
        )
        return component(
            key,
            [
                metric(rule, value, unavailable, failure)
                for rule, value in zip(rules, values, strict=True)
            ],
            scope,
        )
