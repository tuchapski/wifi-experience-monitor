from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from wem.models.metrics import (
    DiagnosticFinding,
    SensorSnapshot,
    ServiceSloMetric,
    ServiceSloMetrics,
)
from wem.profiles.models import (
    ServiceSloTarget,
    ServiceSloThresholds,
    TestConfigurations,
)


@dataclass(frozen=True, slots=True)
class _ServiceSpec:
    key: str
    label: str
    finding_code: str


@dataclass(frozen=True, slots=True)
class _ServiceObservation:
    status: str
    latency_ms: float | None
    packet_loss_percent: float | None


_SERVICES = (
    _ServiceSpec("gateway", "Gateway", "SERVICE_SLO_GATEWAY"),
    _ServiceSpec("internet", "Internet", "SERVICE_SLO_INTERNET"),
    _ServiceSpec("dns", "DNS", "SERVICE_SLO_DNS"),
    _ServiceSpec("https", "HTTPS", "SERVICE_SLO_HTTPS"),
)


@dataclass(slots=True)
class ServiceSloEvaluation:
    metrics: ServiceSloMetrics
    findings: list[DiagnosticFinding]
    fresh_codes: set[str]


class ServiceSloEngine:
    """Evaluate rolling synthetic-service SLOs from fresh test executions only."""

    def __init__(
        self,
        thresholds: ServiceSloThresholds,
        tests: TestConfigurations,
    ) -> None:
        self.thresholds = thresholds.model_copy(deep=True)
        self.tests = tests.model_copy(deep=True)
        self._observations: dict[str, deque[_ServiceObservation]] = {
            spec.key: deque(maxlen=self.thresholds.window_size) for spec in _SERVICES
        }

    def evaluate(self, snapshot: SensorSnapshot) -> ServiceSloEvaluation:
        if not self.thresholds.enabled:
            disabled_services = {
                spec.key: self._disabled_metric(
                    spec, "Synthetic service SLO evaluation is disabled."
                )
                for spec in _SERVICES
            }
            return ServiceSloEvaluation(
                metrics=ServiceSloMetrics(
                    status="disabled",
                    enabled=False,
                    window_size=self.thresholds.window_size,
                    minimum_samples=self.thresholds.minimum_samples,
                    services=disabled_services,
                    fresh=False,
                    reason="Synthetic service SLO evaluation is disabled in the active profile.",
                ),
                findings=[],
                fresh_codes={spec.finding_code for spec in _SERVICES},
            )

        services: dict[str, ServiceSloMetric] = {}
        findings: list[DiagnosticFinding] = []
        fresh_codes: set[str] = set()
        any_fresh = False

        for spec in _SERVICES:
            if not self._test_enabled(spec.key):
                services[spec.key] = self._disabled_metric(
                    spec,
                    f"The {spec.label} synthetic test is disabled.",
                )
                fresh_codes.add(spec.finding_code)
                continue

            outcome = snapshot.connectivity.tests.get(spec.key)
            fresh_definitive = False
            if (
                outcome is not None
                and outcome.fresh
                and outcome.status in {"passed", "failed", "error"}
            ):
                self._observations[spec.key].append(
                    _ServiceObservation(
                        status=outcome.status,
                        latency_ms=(
                            self._latency(snapshot, spec.key)
                            if outcome.status == "passed"
                            else None
                        ),
                        packet_loss_percent=self._packet_loss(snapshot, spec.key),
                    )
                )
                if outcome.status in {"passed", "failed"}:
                    fresh_definitive = True
                    any_fresh = True
                    fresh_codes.add(spec.finding_code)

            metric = self._summarize_service(spec, fresh=fresh_definitive)
            services[spec.key] = metric
            if metric.status in {"warning", "critical"}:
                findings.append(self._finding(spec, metric))

        status = self._overall_status(list(services.values()))
        evaluated = sum(
            metric.status in {"healthy", "warning", "critical"} for metric in services.values()
        )
        if status == "insufficient_data":
            reason = (
                "No enabled synthetic service has enough definitive executions to evaluate "
                "its rolling SLO."
            )
        elif status == "healthy":
            reason = f"{evaluated} synthetic service SLO(s) are within policy."
        elif status == "disabled":
            reason = "All synthetic service SLOs are disabled."
        else:
            reason = f"{len(findings)} synthetic service SLO(s) are outside policy."

        return ServiceSloEvaluation(
            metrics=ServiceSloMetrics(
                status=status,
                enabled=True,
                window_size=self.thresholds.window_size,
                minimum_samples=self.thresholds.minimum_samples,
                services=services,
                fresh=any_fresh,
                reason=reason,
            ),
            findings=findings,
            fresh_codes=fresh_codes,
        )

    def _summarize_service(self, spec: _ServiceSpec, *, fresh: bool) -> ServiceSloMetric:
        observations = list(self._observations[spec.key])
        target = self._target(spec.key)
        measurable = [item for item in observations if item.status in {"passed", "failed"}]
        successes = [item for item in measurable if item.status == "passed"]
        failures = [item for item in measurable if item.status == "failed"]
        errors = sum(item.status == "error" for item in observations)
        availability = round(len(successes) * 100.0 / len(measurable), 3) if measurable else None
        latencies = [
            item.latency_ms
            for item in successes
            if item.latency_ms is not None and math.isfinite(item.latency_ms)
        ]
        losses = [
            item.packet_loss_percent
            for item in measurable
            if item.packet_loss_percent is not None and math.isfinite(item.packet_loss_percent)
        ]
        latency_p95 = self._percentile(latencies, 0.95)
        loss_p95 = self._percentile(losses, 0.95)

        dimension_statuses: list[str] = []
        violations: list[str] = []

        if len(measurable) >= self.thresholds.minimum_samples and availability is not None:
            availability_status = self._availability_status(availability, target)
            dimension_statuses.append(availability_status)
            if availability_status in {"warning", "critical"}:
                violations.append(f"availability {availability:g}%")

        if len(latencies) >= self.thresholds.minimum_samples and latency_p95 is not None:
            latency_status = self._latency_status(latency_p95, target)
            dimension_statuses.append(latency_status)
            if latency_status in {"warning", "critical"}:
                violations.append(f"latency P95 {latency_p95:g} ms")

        packet_policy = (
            target.packet_loss_p95_warning_percent is not None
            and target.packet_loss_p95_critical_percent is not None
        )
        if (
            packet_policy
            and len(losses) >= self.thresholds.minimum_samples
            and loss_p95 is not None
        ):
            loss_status = self._packet_loss_status(loss_p95, target)
            dimension_statuses.append(loss_status)
            if loss_status in {"warning", "critical"}:
                violations.append(f"packet-loss P95 {loss_p95:g}%")

        if not dimension_statuses:
            status = "insufficient_data"
            reason = (
                f"{len(measurable)}/{self.thresholds.minimum_samples} definitive executions; "
                f"{len(latencies)} latency samples are available."
            )
        else:
            status = self._worst_status(dimension_statuses)
            reason = (
                "Rolling SLO is within policy."
                if status == "healthy"
                else "Rolling SLO violation: " + ", ".join(violations) + "."
            )

        return ServiceSloMetric(
            service=spec.key,
            status=status,
            attempt_count=len(observations),
            measurable_count=len(measurable),
            success_count=len(successes),
            failure_count=len(failures),
            measurement_error_count=errors,
            availability_percent=availability,
            latency_sample_count=len(latencies),
            latency_p95_ms=latency_p95,
            packet_loss_sample_count=len(losses),
            packet_loss_p95_percent=loss_p95,
            availability_warning_percent=target.availability_warning_percent,
            availability_critical_percent=target.availability_critical_percent,
            latency_p95_warning_ms=target.latency_p95_warning_ms,
            latency_p95_critical_ms=target.latency_p95_critical_ms,
            packet_loss_p95_warning_percent=target.packet_loss_p95_warning_percent,
            packet_loss_p95_critical_percent=target.packet_loss_p95_critical_percent,
            fresh=fresh,
            reason=reason,
        )

    def _disabled_metric(self, spec: _ServiceSpec, reason: str) -> ServiceSloMetric:
        target = self._target(spec.key)
        return ServiceSloMetric(
            service=spec.key,
            status="disabled",
            attempt_count=0,
            measurable_count=0,
            success_count=0,
            failure_count=0,
            measurement_error_count=0,
            availability_percent=None,
            latency_sample_count=0,
            latency_p95_ms=None,
            packet_loss_sample_count=0,
            packet_loss_p95_percent=None,
            availability_warning_percent=target.availability_warning_percent,
            availability_critical_percent=target.availability_critical_percent,
            latency_p95_warning_ms=target.latency_p95_warning_ms,
            latency_p95_critical_ms=target.latency_p95_critical_ms,
            packet_loss_p95_warning_percent=target.packet_loss_p95_warning_percent,
            packet_loss_p95_critical_percent=target.packet_loss_p95_critical_percent,
            fresh=False,
            reason=reason,
        )

    def _finding(self, spec: _ServiceSpec, metric: ServiceSloMetric) -> DiagnosticFinding:
        return DiagnosticFinding(
            severity=metric.status,
            domain="service_slo",
            code=spec.finding_code,
            message=(
                f"{spec.label} rolling SLO is {metric.status}: "
                f"availability {self._format(metric.availability_percent, '%')}, "
                f"latency P95 {self._format(metric.latency_p95_ms, ' ms')}, "
                f"packet-loss P95 {self._format(metric.packet_loss_p95_percent, '%')}."
            ),
        )

    def _target(self, key: str) -> ServiceSloTarget:
        if key == "gateway":
            return self.thresholds.gateway
        if key == "internet":
            return self.thresholds.internet
        if key == "dns":
            return self.thresholds.dns
        if key == "https":
            return self.thresholds.https
        raise ValueError(f"Unsupported service SLO key: {key}")

    def _test_enabled(self, key: str) -> bool:
        if key == "gateway":
            return self.tests.gateway.enabled
        if key == "internet":
            return self.tests.internet.enabled
        if key == "dns":
            return self.tests.dns.enabled
        if key == "https":
            return self.tests.https.enabled
        raise ValueError(f"Unsupported synthetic test key: {key}")

    @staticmethod
    def _latency(snapshot: SensorSnapshot, key: str) -> float | None:
        if key == "gateway":
            return ServiceSloEngine._numeric(snapshot.connectivity.gateway_latency_avg_ms)
        if key == "internet":
            return ServiceSloEngine._numeric(snapshot.connectivity.internet_latency_avg_ms)
        if key == "dns":
            return ServiceSloEngine._numeric(snapshot.connectivity.dns_latency_ms)
        if key == "https":
            return ServiceSloEngine._numeric(snapshot.connectivity.https_total_time_ms)
        return None

    @staticmethod
    def _packet_loss(snapshot: SensorSnapshot, key: str) -> float | None:
        if key == "gateway":
            return ServiceSloEngine._numeric(snapshot.connectivity.gateway_packet_loss_percent)
        if key == "internet":
            return ServiceSloEngine._numeric(snapshot.connectivity.internet_packet_loss_percent)
        return None

    @staticmethod
    def _availability_status(value: float, target: ServiceSloTarget) -> str:
        if value < target.availability_critical_percent:
            return "critical"
        if value < target.availability_warning_percent:
            return "warning"
        return "healthy"

    @staticmethod
    def _latency_status(value: float, target: ServiceSloTarget) -> str:
        if value >= target.latency_p95_critical_ms:
            return "critical"
        if value >= target.latency_p95_warning_ms:
            return "warning"
        return "healthy"

    @staticmethod
    def _packet_loss_status(value: float, target: ServiceSloTarget) -> str:
        critical = target.packet_loss_p95_critical_percent
        warning = target.packet_loss_p95_warning_percent
        if critical is None or warning is None:
            return "healthy"
        if value >= critical:
            return "critical"
        if value >= warning:
            return "warning"
        return "healthy"

    @staticmethod
    def _worst_status(statuses: list[str]) -> str:
        if "critical" in statuses:
            return "critical"
        if "warning" in statuses:
            return "warning"
        return "healthy"

    @staticmethod
    def _overall_status(metrics: list[ServiceSloMetric]) -> str:
        statuses = [metric.status for metric in metrics]
        if "critical" in statuses:
            return "critical"
        if "warning" in statuses:
            return "warning"
        if "healthy" in statuses:
            return "healthy"
        if "insufficient_data" in statuses:
            return "insufficient_data"
        return "disabled"

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 3)

    @staticmethod
    def _numeric(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    @staticmethod
    def _format(value: float | None, suffix: str) -> str:
        return "unavailable" if value is None else f"{value:g}{suffix}"
