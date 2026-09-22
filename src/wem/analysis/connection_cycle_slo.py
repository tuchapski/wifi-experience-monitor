import math
from collections import deque
from dataclasses import dataclass

from wem.models.metrics import (
    ConnectionCycleMetrics,
    ConnectionCycleSloMetrics,
    ConnectionStageSloMetric,
    DiagnosticFinding,
)
from wem.profiles.models import ConnectionCycleThresholds


@dataclass(frozen=True, slots=True)
class _StageSpec:
    key: str
    cycle_key: str
    label: str
    finding_code: str


_STAGE_SPECS = (
    _StageSpec(
        "association",
        "association",
        "Association",
        "CONNECTION_CYCLE_ASSOCIATION_P95_SLO",
    ),
    _StageSpec(
        "authentication",
        "authentication",
        "Authentication",
        "CONNECTION_CYCLE_AUTHENTICATION_P95_SLO",
    ),
    _StageSpec(
        "ipv4",
        "dhcp",
        "IPv4 address",
        "CONNECTION_CYCLE_IPV4_P95_SLO",
    ),
    _StageSpec(
        "gateway",
        "gateway",
        "Gateway reachable",
        "CONNECTION_CYCLE_GATEWAY_P95_SLO",
    ),
    _StageSpec(
        "dns",
        "dns",
        "DNS resolution",
        "CONNECTION_CYCLE_DNS_P95_SLO",
    ),
)

_TOTAL_FINDING_CODE = "CONNECTION_CYCLE_P95_SLO"


@dataclass(slots=True)
class ConnectionCycleSloEvaluation:
    metrics: ConnectionCycleSloMetrics
    findings: list[DiagnosticFinding]
    fresh_codes: set[str]


class ConnectionCycleSloEngine:
    """Evaluate rolling P95 for network ready and connection-stage milestones."""

    def __init__(self, thresholds: ConnectionCycleThresholds):
        self.thresholds = thresholds.model_copy(deep=True)
        self._durations: deque[float] = deque(maxlen=self.thresholds.window_size)
        self._last_ingested_session_id: str | None = None
        self._stage_durations: dict[str, deque[float]] = {
            spec.key: deque(maxlen=self.thresholds.window_size) for spec in _STAGE_SPECS
        }
        self._last_stage_session_id: dict[str, str | None] = {
            spec.key: None for spec in _STAGE_SPECS
        }

    def observe(
        self,
        cycle: ConnectionCycleMetrics | None,
    ) -> ConnectionCycleSloEvaluation:
        total_fresh, latest_cycle_ms = self._ingest_total(cycle)
        total_p95_ms = self._percentile(list(self._durations), 0.95)
        total_sample_count = len(self._durations)
        total_status, total_reason = self._status(
            label="Network-ready",
            p95_ms=total_p95_ms,
            sample_count=total_sample_count,
            minimum_samples=self.thresholds.minimum_samples,
            warning_ms=self.thresholds.p95_warning_ms,
            critical_ms=self.thresholds.p95_critical_ms,
        )

        findings: list[DiagnosticFinding] = []
        fresh_codes: set[str] = set()
        if total_status in {"warning", "critical"} and total_p95_ms is not None:
            findings.append(
                self._finding(
                    severity=total_status,
                    code=_TOTAL_FINDING_CODE,
                    label="Connection-cycle network-ready",
                    p95_ms=total_p95_ms,
                    sample_count=total_sample_count,
                    warning_ms=self.thresholds.p95_warning_ms,
                    critical_ms=self.thresholds.p95_critical_ms,
                )
            )
        if total_fresh and total_sample_count >= self.thresholds.minimum_samples:
            fresh_codes.add(_TOTAL_FINDING_CODE)

        stage_results: dict[str, ConnectionStageSloMetric] = {}
        any_stage_fresh = False
        for spec in _STAGE_SPECS:
            stage_fresh, latest_ms = self._ingest_stage(cycle, spec)
            any_stage_fresh = any_stage_fresh or stage_fresh
            values = list(self._stage_durations[spec.key])
            p95_ms = self._percentile(values, 0.95)
            sample_count = len(values)
            stage_thresholds = getattr(self.thresholds.stages, spec.key)
            status, reason = self._status(
                label=spec.label,
                p95_ms=p95_ms,
                sample_count=sample_count,
                minimum_samples=self.thresholds.minimum_samples,
                warning_ms=stage_thresholds.p95_warning_ms,
                critical_ms=stage_thresholds.p95_critical_ms,
            )
            stage_results[spec.key] = ConnectionStageSloMetric(
                stage=spec.key,
                label=spec.label,
                status=status,
                sample_count=sample_count,
                minimum_samples=self.thresholds.minimum_samples,
                p95_ms=p95_ms,
                warning_threshold_ms=stage_thresholds.p95_warning_ms,
                critical_threshold_ms=stage_thresholds.p95_critical_ms,
                latest_ms=latest_ms,
                fresh=stage_fresh,
                reason=reason,
            )
            if status in {"warning", "critical"} and p95_ms is not None:
                findings.append(
                    self._finding(
                        severity=status,
                        code=spec.finding_code,
                        label=spec.label,
                        p95_ms=p95_ms,
                        sample_count=sample_count,
                        warning_ms=stage_thresholds.p95_warning_ms,
                        critical_ms=stage_thresholds.p95_critical_ms,
                    )
                )
            if stage_fresh and sample_count >= self.thresholds.minimum_samples:
                fresh_codes.add(spec.finding_code)

        overall_status = self._overall_status(total_status, stage_results)
        if findings:
            reason = (
                f"{len(findings)} connection-cycle SLO policy/policies are currently violated. "
                "Stage P95 values are time from connection start to each observed milestone."
            )
        elif overall_status == "insufficient_data":
            reason = "No connection-cycle SLO policy has enough measured cycles to evaluate yet."
        else:
            evaluated = sum(
                metric.status != "insufficient_data" for metric in stage_results.values()
            ) + (total_status != "insufficient_data")
            reason = (
                f"{evaluated} connection-cycle SLO policy/policies are within threshold. "
                "Stage P95 values are time from connection start to each observed milestone."
            )

        return ConnectionCycleSloEvaluation(
            metrics=ConnectionCycleSloMetrics(
                status=overall_status,
                sample_count=total_sample_count,
                minimum_samples=self.thresholds.minimum_samples,
                window_size=self.thresholds.window_size,
                p95_ms=total_p95_ms,
                warning_threshold_ms=self.thresholds.p95_warning_ms,
                critical_threshold_ms=self.thresholds.p95_critical_ms,
                latest_cycle_ms=latest_cycle_ms,
                fresh=total_fresh or any_stage_fresh,
                reason=reason,
                stages=stage_results,
            ),
            findings=findings,
            fresh_codes=fresh_codes,
        )

    def _ingest_total(
        self,
        cycle: ConnectionCycleMetrics | None,
    ) -> tuple[bool, float | None]:
        if not self._measurable(cycle):
            return False, None
        assert cycle is not None
        value = cycle.total_time_ms
        assert value is not None
        if cycle.session_id == self._last_ingested_session_id:
            return False, None
        latest = float(value)
        self._durations.append(latest)
        self._last_ingested_session_id = cycle.session_id
        return True, latest

    def _ingest_stage(
        self,
        cycle: ConnectionCycleMetrics | None,
        spec: _StageSpec,
    ) -> tuple[bool, float | None]:
        if cycle is None or cycle.session_type == "observed_existing":
            return False, None
        stage = cycle.stages.get(spec.cycle_key)
        if stage is None or stage.status != "observed":
            return False, None
        value = stage.elapsed_ms
        if not self._numeric(value):
            return False, None
        assert value is not None
        if cycle.session_id == self._last_stage_session_id[spec.key]:
            return False, None
        latest = float(value)
        self._stage_durations[spec.key].append(latest)
        self._last_stage_session_id[spec.key] = cycle.session_id
        return True, latest

    @staticmethod
    def _status(
        *,
        label: str,
        p95_ms: float | None,
        sample_count: int,
        minimum_samples: int,
        warning_ms: float,
        critical_ms: float,
    ) -> tuple[str, str]:
        if sample_count < minimum_samples:
            return (
                "insufficient_data",
                f"{sample_count}/{minimum_samples} measured {label.lower()} milestones are "
                "available; this P95 is not evaluated yet.",
            )
        assert p95_ms is not None
        if p95_ms >= critical_ms:
            status = "critical"
            threshold = critical_ms
        elif p95_ms >= warning_ms:
            status = "warning"
            threshold = warning_ms
        else:
            return (
                "healthy",
                f"{label} P95 is {p95_ms:.3f} ms across {sample_count} measured cycles.",
            )
        return (
            status,
            f"{label} P95 is {p95_ms:.3f} ms across {sample_count} measured cycles, "
            f"above the {threshold:g} ms {status} threshold.",
        )

    @staticmethod
    def _finding(
        *,
        severity: str,
        code: str,
        label: str,
        p95_ms: float,
        sample_count: int,
        warning_ms: float,
        critical_ms: float,
    ) -> DiagnosticFinding:
        threshold = critical_ms if severity == "critical" else warning_ms
        return DiagnosticFinding(
            severity=severity,
            domain="connection_cycle",
            code=code,
            message=(
                f"{label} P95 is {p95_ms:.3f} ms across {sample_count} measured cycles, "
                f"above the {threshold:g} ms {severity} threshold."
            ),
        )

    @staticmethod
    def _overall_status(
        total_status: str,
        stages: dict[str, ConnectionStageSloMetric],
    ) -> str:
        statuses = [total_status, *(metric.status for metric in stages.values())]
        if "critical" in statuses:
            return "critical"
        if "warning" in statuses:
            return "warning"
        if "healthy" in statuses:
            return "healthy"
        return "insufficient_data"

    @staticmethod
    def _measurable(cycle: ConnectionCycleMetrics | None) -> bool:
        if cycle is None or cycle.session_type == "observed_existing":
            return False
        value = cycle.total_time_ms
        return cycle.state in {"ready", "disconnected"} and ConnectionCycleSloEngine._numeric(value)

    @staticmethod
    def _numeric(value: object) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) >= 0.0
        )

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
