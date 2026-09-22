import math
from collections import deque
from dataclasses import dataclass

from wem.models.metrics import (
    ConnectionCycleMetrics,
    ConnectionCycleSloMetrics,
    DiagnosticFinding,
)
from wem.profiles.models import ConnectionCycleThresholds


@dataclass(slots=True)
class ConnectionCycleSloEvaluation:
    metrics: ConnectionCycleSloMetrics
    finding: DiagnosticFinding | None


class ConnectionCycleSloEngine:
    """Evaluate rolling P95 using only unique, measurable connection cycles."""

    def __init__(self, thresholds: ConnectionCycleThresholds):
        self.thresholds = thresholds.model_copy(deep=True)
        self._durations: deque[float] = deque(maxlen=self.thresholds.window_size)
        self._last_ingested_session_id: str | None = None

    def observe(
        self,
        cycle: ConnectionCycleMetrics | None,
    ) -> ConnectionCycleSloEvaluation:
        fresh = False
        latest_cycle_ms: float | None = None

        if self._measurable(cycle):
            assert cycle is not None
            value = cycle.total_time_ms
            assert value is not None
            if cycle.session_id != self._last_ingested_session_id:
                latest_cycle_ms = float(value)
                self._durations.append(latest_cycle_ms)
                self._last_ingested_session_id = cycle.session_id
                fresh = True

        values = list(self._durations)
        p95_ms = self._percentile(values, 0.95)
        sample_count = len(values)

        if sample_count < self.thresholds.minimum_samples:
            status = "insufficient_data"
            finding = None
            reason = (
                f"{sample_count}/{self.thresholds.minimum_samples} measurable cycles are "
                "available; the SLO is not evaluated yet."
            )
        elif p95_ms is not None and p95_ms >= self.thresholds.p95_critical_ms:
            status = "critical"
            finding = self._finding("critical", p95_ms, sample_count)
            reason = finding.message
        elif p95_ms is not None and p95_ms >= self.thresholds.p95_warning_ms:
            status = "warning"
            finding = self._finding("warning", p95_ms, sample_count)
            reason = finding.message
        else:
            status = "healthy"
            finding = None
            reason = (
                f"Rolling network-ready P95 is {p95_ms:.3f} ms across {sample_count} "
                "measurable cycles."
                if p95_ms is not None
                else "No measurable connection cycles are available."
            )

        return ConnectionCycleSloEvaluation(
            metrics=ConnectionCycleSloMetrics(
                status=status,
                sample_count=sample_count,
                minimum_samples=self.thresholds.minimum_samples,
                window_size=self.thresholds.window_size,
                p95_ms=p95_ms,
                warning_threshold_ms=self.thresholds.p95_warning_ms,
                critical_threshold_ms=self.thresholds.p95_critical_ms,
                latest_cycle_ms=latest_cycle_ms,
                fresh=fresh,
                reason=reason,
            ),
            finding=finding,
        )

    def _finding(
        self,
        severity: str,
        p95_ms: float,
        sample_count: int,
    ) -> DiagnosticFinding:
        threshold = (
            self.thresholds.p95_critical_ms
            if severity == "critical"
            else self.thresholds.p95_warning_ms
        )
        return DiagnosticFinding(
            severity=severity,
            domain="connection_cycle",
            code="CONNECTION_CYCLE_P95_SLO",
            message=(
                f"Connection-cycle network-ready P95 is {p95_ms:.3f} ms across "
                f"{sample_count} measured cycles, above the {threshold:g} ms "
                f"{severity} threshold."
            ),
        )

    @staticmethod
    def _measurable(cycle: ConnectionCycleMetrics | None) -> bool:
        if cycle is None or cycle.session_type == "observed_existing":
            return False
        value = cycle.total_time_ms
        return (
            cycle.state in {"ready", "disconnected"}
            and isinstance(value, (int, float))
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
