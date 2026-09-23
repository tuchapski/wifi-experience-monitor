from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from statistics import median

from wem.models.metrics import (
    AdaptiveBaselineMetric,
    AdaptiveBaselineMetrics,
    DiagnosticFinding,
    SensorSnapshot,
)
from wem.profiles.models import AdaptiveBaselineThresholds


@dataclass(frozen=True, slots=True)
class _MetricSpec:
    key: str
    label: str
    unit: str
    direction: str
    scale_floor: float
    finding_code: str


_METRICS = (
    _MetricSpec("signal_dbm", "RSSI", "dBm", "lower_is_worse", 2.0, "BASELINE_RSSI_DEVIATION"),
    _MetricSpec(
        "tx_retries_per_100_packets",
        "TX retries",
        "retries / 100 TX",
        "higher_is_worse",
        2.0,
        "BASELINE_TX_RETRIES_DEVIATION",
    ),
    _MetricSpec(
        "gateway_latency_avg_ms",
        "Gateway latency",
        "ms",
        "higher_is_worse",
        2.0,
        "BASELINE_GATEWAY_LATENCY_DEVIATION",
    ),
    _MetricSpec(
        "internet_latency_avg_ms",
        "Internet latency",
        "ms",
        "higher_is_worse",
        5.0,
        "BASELINE_INTERNET_LATENCY_DEVIATION",
    ),
    _MetricSpec(
        "dns_latency_ms",
        "DNS latency",
        "ms",
        "higher_is_worse",
        5.0,
        "BASELINE_DNS_LATENCY_DEVIATION",
    ),
    _MetricSpec(
        "https_total_time_ms",
        "HTTPS response",
        "ms",
        "higher_is_worse",
        20.0,
        "BASELINE_HTTPS_RESPONSE_DEVIATION",
    ),
    _MetricSpec(
        "connection_cycle_p95_ms",
        "Connection-cycle P95",
        "ms",
        "higher_is_worse",
        250.0,
        "BASELINE_CONNECTION_CYCLE_P95_DEVIATION",
    ),
)


@dataclass(slots=True)
class AdaptiveBaselineEvaluation:
    metrics: AdaptiveBaselineMetrics
    findings: list[DiagnosticFinding]
    fresh_codes: set[str]


class AdaptiveBaselineEngine:
    """Compare fresh measurements with a robust same-SSID historical baseline."""

    def __init__(self, thresholds: AdaptiveBaselineThresholds):
        self.thresholds = thresholds.model_copy(deep=True)
        self._ssid: str | None = None
        self._reference: dict[str, deque[float]] = {
            spec.key: deque(maxlen=self.thresholds.max_samples) for spec in _METRICS
        }

    def seed(self, ssid: str | None, reference_values: dict[str, list[float]]) -> None:
        """Replace the in-memory baseline when monitoring moves to another SSID."""
        self._ssid = ssid
        for spec in _METRICS:
            values = [value for value in reference_values.get(spec.key, []) if math.isfinite(value)]
            self._reference[spec.key] = deque(
                values[-self.thresholds.max_samples :],
                maxlen=self.thresholds.max_samples,
            )

    def evaluate(
        self,
        snapshot: SensorSnapshot,
    ) -> AdaptiveBaselineEvaluation:
        ssid = snapshot.wifi.ssid
        if not self.thresholds.enabled:
            return AdaptiveBaselineEvaluation(
                metrics=self._disabled(ssid),
                findings=[],
                fresh_codes=set(),
            )

        if ssid != self._ssid:
            self.seed(ssid, {})

        current_values = self._current_values(snapshot)
        metric_results: list[AdaptiveBaselineMetric] = []
        findings: list[DiagnosticFinding] = []
        fresh_codes: set[str] = set()

        for spec in _METRICS:
            result = self._evaluate_metric(
                spec,
                current_values.get(spec.key),
                list(self._reference[spec.key]),
            )
            metric_results.append(result)
            if result.status not in {"unavailable", "insufficient_data"}:
                fresh_codes.add(spec.finding_code)
            if result.status in {"warning", "critical"}:
                findings.append(self._finding(spec, result))

        status = self._overall_status(metric_results)
        evaluated = sum(
            item.status not in {"unavailable", "insufficient_data"} for item in metric_results
        )
        if status == "insufficient_data":
            reason = (
                "No metric has enough same-SSID historical samples to evaluate "
                "the adaptive baseline."
            )
        elif status == "healthy":
            reason = f"{evaluated} metric(s) are within their robust same-SSID baseline."
        else:
            reason = f"{len(findings)} metric(s) deviate from their robust same-SSID baseline."

        self._learn(current_values, metric_results)

        return AdaptiveBaselineEvaluation(
            metrics=AdaptiveBaselineMetrics(
                status=status,
                ssid=ssid,
                lookback_hours=self.thresholds.lookback_hours,
                minimum_samples=self.thresholds.minimum_samples,
                max_samples=self.thresholds.max_samples,
                warning_sigma=self.thresholds.warning_sigma,
                critical_sigma=self.thresholds.critical_sigma,
                metrics=metric_results,
                fresh=bool(fresh_codes),
                reason=reason,
            ),
            findings=findings,
            fresh_codes=fresh_codes,
        )

    def _learn(
        self,
        current_values: dict[str, float | None],
        metrics: list[AdaptiveBaselineMetric],
    ) -> None:
        if self._ssid is None:
            return
        by_key = {metric.key: metric for metric in metrics}
        for spec in _METRICS:
            current = current_values.get(spec.key)
            metric = by_key[spec.key]
            if current is None or metric.status in {"warning", "critical"}:
                continue
            self._reference[spec.key].append(current)

    def _evaluate_metric(
        self,
        spec: _MetricSpec,
        current: float | None,
        reference: list[float],
    ) -> AdaptiveBaselineMetric:
        values = [value for value in reference if math.isfinite(value)]
        sample_count = len(values)
        if current is None or not math.isfinite(current):
            return self._metric_result(
                spec,
                status="unavailable",
                current=None,
                sample_count=sample_count,
                reason="The current measurement is unavailable or not fresh.",
            )
        if sample_count < self.thresholds.minimum_samples:
            return self._metric_result(
                spec,
                status="insufficient_data",
                current=current,
                sample_count=sample_count,
                reason=(
                    f"{sample_count}/{self.thresholds.minimum_samples} same-SSID reference "
                    "samples are available."
                ),
            )

        center = float(median(values))
        mad = float(median(abs(value - center) for value in values))
        robust_sigma = max(1.4826 * mad, spec.scale_floor)
        adverse_delta = center - current if spec.direction == "lower_is_worse" else current - center
        deviation_sigma = adverse_delta / robust_sigma

        if deviation_sigma >= self.thresholds.critical_sigma:
            status = "critical"
        elif deviation_sigma >= self.thresholds.warning_sigma:
            status = "warning"
        else:
            status = "healthy"

        direction_text = "worse" if deviation_sigma > 0 else "better or equal"
        return AdaptiveBaselineMetric(
            key=spec.key,
            label=spec.label,
            unit=spec.unit,
            status=status,
            current=round(current, 3),
            baseline_median=round(center, 3),
            baseline_mad=round(mad, 3),
            robust_sigma=round(robust_sigma, 3),
            deviation_sigma=round(deviation_sigma, 3),
            sample_count=sample_count,
            minimum_samples=self.thresholds.minimum_samples,
            reason=(
                f"Current value is {abs(deviation_sigma):.2f} robust sigma {direction_text} "
                "than the same-SSID median."
            ),
        )

    def _metric_result(
        self,
        spec: _MetricSpec,
        *,
        status: str,
        current: float | None,
        sample_count: int,
        reason: str,
    ) -> AdaptiveBaselineMetric:
        return AdaptiveBaselineMetric(
            key=spec.key,
            label=spec.label,
            unit=spec.unit,
            status=status,
            current=current,
            baseline_median=None,
            baseline_mad=None,
            robust_sigma=None,
            deviation_sigma=None,
            sample_count=sample_count,
            minimum_samples=self.thresholds.minimum_samples,
            reason=reason,
        )

    def _finding(
        self,
        spec: _MetricSpec,
        metric: AdaptiveBaselineMetric,
    ) -> DiagnosticFinding:
        assert metric.deviation_sigma is not None
        assert metric.current is not None
        assert metric.baseline_median is not None
        return DiagnosticFinding(
            severity=metric.status,
            domain="baseline",
            code=spec.finding_code,
            message=(
                f"{spec.label} is {metric.deviation_sigma:.2f} robust sigma worse than its "
                f"same-SSID baseline: current {metric.current:g} {spec.unit}, median "
                f"{metric.baseline_median:g} {spec.unit}."
            ),
        )

    def _current_values(self, snapshot: SensorSnapshot) -> dict[str, float | None]:
        connectivity = snapshot.connectivity
        cycle_slo = snapshot.connection_cycle_slo
        return {
            "signal_dbm": self._numeric(snapshot.wifi.signal_dbm),
            "tx_retries_per_100_packets": self._numeric(
                snapshot.wifi_delta.tx_retries_per_100_packets
                if snapshot.wifi_delta is not None
                else None
            ),
            "gateway_latency_avg_ms": self._fresh_connectivity(
                snapshot, "gateway", connectivity.gateway_latency_avg_ms
            ),
            "internet_latency_avg_ms": self._fresh_connectivity(
                snapshot, "internet", connectivity.internet_latency_avg_ms
            ),
            "dns_latency_ms": self._fresh_connectivity(
                snapshot, "dns", connectivity.dns_latency_ms
            ),
            "https_total_time_ms": self._fresh_connectivity(
                snapshot, "https", connectivity.https_total_time_ms
            ),
            "connection_cycle_p95_ms": (
                self._numeric(cycle_slo.p95_ms)
                if cycle_slo is not None
                and cycle_slo.fresh
                and cycle_slo.status != "insufficient_data"
                else None
            ),
        }

    @staticmethod
    def _fresh_connectivity(
        snapshot: SensorSnapshot,
        name: str,
        value: float | None,
    ) -> float | None:
        outcome = snapshot.connectivity.tests.get(name)
        if outcome is not None and not outcome.fresh:
            return None
        return AdaptiveBaselineEngine._numeric(value)

    @staticmethod
    def _numeric(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    @staticmethod
    def _overall_status(metrics: list[AdaptiveBaselineMetric]) -> str:
        if any(item.status == "critical" for item in metrics):
            return "critical"
        if any(item.status == "warning" for item in metrics):
            return "warning"
        if any(item.status == "healthy" for item in metrics):
            return "healthy"
        return "insufficient_data"

    def _disabled(self, ssid: str | None) -> AdaptiveBaselineMetrics:
        return AdaptiveBaselineMetrics(
            status="disabled",
            ssid=ssid,
            lookback_hours=self.thresholds.lookback_hours,
            minimum_samples=self.thresholds.minimum_samples,
            max_samples=self.thresholds.max_samples,
            warning_sigma=self.thresholds.warning_sigma,
            critical_sigma=self.thresholds.critical_sigma,
            metrics=[],
            fresh=False,
            reason="Adaptive baseline evaluation is disabled by the active test profile.",
        )
