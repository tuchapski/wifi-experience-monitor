"""Raw-metric comparison around a focused diagnostic window."""

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.recording_models import RecordingMetric
from wifi_server.recording_schemas import (
    DiagnosticFinding,
    DiagnosticMetricComparison,
    DiagnosticMetricStatistics,
    DiagnosticWindowComparison,
)


def _statistics(
    rows: list[tuple[str, int, float | None, float | None, float | None]],
) -> dict[str, DiagnosticMetricStatistics]:
    return {
        metric: DiagnosticMetricStatistics(
            sample_count=count,
            minimum=minimum,
            average=average,
            maximum=maximum,
        )
        for metric, count, minimum, average, maximum in rows
    }


def _period_statistics(
    session: Session,
    recording_id: str,
    metrics: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, DiagnosticMetricStatistics]:
    statement = (
        select(
            RecordingMetric.metric,
            func.count(RecordingMetric.id),
            func.min(RecordingMetric.value),
            func.avg(RecordingMetric.value),
            func.max(RecordingMetric.value),
        )
        .where(
            RecordingMetric.recording_id == recording_id,
            RecordingMetric.metric.in_(metrics),
            RecordingMetric.observed_at >= start,
            RecordingMetric.observed_at < end,
        )
        .group_by(RecordingMetric.metric)
    )
    return _statistics(list(session.execute(statement)))


# Minimum change in the mean required before a metric becomes a diagnostic finding.
# Direction indicates which movement represents deterioration for that metric.
_FINDING_RULES: dict[str, tuple[float, str]] = {
    "wifi.rssi_dbm": (5.0, "decrease"),
    "wifi.signal_avg_dbm": (5.0, "decrease"),
    "wifi.snr_db": (5.0, "decrease"),
    "wifi.tx_rate_mbps": (20.0, "decrease"),
    "wifi.rx_rate_mbps": (20.0, "decrease"),
    "wifi.tx_retries_per_100": (5.0, "increase"),
    "wifi.tx_failed_pct": (2.0, "increase"),
    "wifi.channel_utilization_pct": (15.0, "increase"),
    "wifi.airtime_rx_pct": (15.0, "increase"),
    "wifi.airtime_tx_pct": (15.0, "increase"),
    "wifi.noise_dbm": (5.0, "increase"),
}


def _recovery_state(
    baseline: float,
    during: float,
    after: float | None,
    threshold: float,
) -> str:
    if after is None:
        return "unknown"
    if abs(after - baseline) < threshold:
        return "recovered"
    during_distance = abs(during - baseline)
    after_distance = abs(after - baseline)
    if after_distance < during_distance:
        return "partial"
    return "not_recovered"


def _finding_for_comparison(comparison: DiagnosticMetricComparison) -> DiagnosticFinding | None:
    rule = _FINDING_RULES.get(comparison.metric)
    baseline = comparison.before.average
    during = comparison.during.average
    if rule is None or baseline is None or during is None:
        return None

    threshold, deteriorating_direction = rule
    delta = during - baseline
    deteriorated = (
        delta <= -threshold if deteriorating_direction == "decrease" else delta >= threshold
    )
    if not deteriorated:
        return None

    return DiagnosticFinding(
        metric=comparison.metric,
        direction="decreased" if delta < 0 else "increased",
        baseline=baseline,
        during=during,
        delta=delta,
        after=comparison.after.average,
        recovery=_recovery_state(
            baseline,
            during,
            comparison.after.average,
            threshold,
        ),
    )


def _findings(comparisons: list[DiagnosticMetricComparison]) -> list[DiagnosticFinding]:
    return [
        finding for comparison in comparisons if (finding := _finding_for_comparison(comparison))
    ]


def compare_diagnostic_window(
    session: Session,
    recording_id: str,
    metrics: list[str],
    window_start: datetime,
    window_end: datetime,
    context_seconds: int,
) -> DiagnosticWindowComparison:
    """Compare raw observations before, during, and after a degraded interval."""
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    if window_end <= window_start:
        raise HTTPException(status_code=422, detail="window_end must be after window_start")

    recording_start = recording.started_at or recording.created_at
    recording_end = recording.ended_at
    before_start = max(recording_start, window_start - timedelta(seconds=context_seconds))
    after_end = window_end + timedelta(seconds=context_seconds)
    if recording_end is not None:
        after_end = min(recording_end, after_end)

    before = _period_statistics(session, recording_id, metrics, before_start, window_start)
    during = _period_statistics(session, recording_id, metrics, window_start, window_end)
    after = _period_statistics(session, recording_id, metrics, window_end, after_end)

    empty = DiagnosticMetricStatistics(sample_count=0)
    comparisons = [
        DiagnosticMetricComparison(
            metric=metric,
            before=before.get(metric, empty),
            during=during.get(metric, empty),
            after=after.get(metric, empty),
        )
        for metric in metrics
    ]
    return DiagnosticWindowComparison(
        window_start=window_start,
        window_end=window_end,
        context_seconds=context_seconds,
        before_start=before_start,
        after_end=after_end,
        metrics=comparisons,
        findings=_findings(comparisons),
    )
