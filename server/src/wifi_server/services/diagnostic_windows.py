"""Raw-metric comparison around a focused diagnostic window."""

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.recording_models import RecordingMetric
from wifi_server.diagnostic_policy import (
    EVIDENCE_DOMAIN_ORDER,
    FINDING_RULES,
    METRIC_EVIDENCE_DOMAIN,
)
from wifi_server.recording_schemas import (
    DiagnosticEvidenceDomainSummary,
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
    rule = FINDING_RULES.get(comparison.metric)
    evidence_domain = METRIC_EVIDENCE_DOMAIN.get(comparison.metric)
    baseline = comparison.before.average
    during = comparison.during.average
    if rule is None or evidence_domain is None or baseline is None or during is None:
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
        evidence_domain=evidence_domain,
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


def _evidence_domains(
    comparisons: list[DiagnosticMetricComparison],
    findings: list[DiagnosticFinding],
) -> list[DiagnosticEvidenceDomainSummary]:
    summaries: list[DiagnosticEvidenceDomainSummary] = []
    for domain in EVIDENCE_DOMAIN_ORDER:
        evaluated_metrics = [
            comparison.metric
            for comparison in comparisons
            if METRIC_EVIDENCE_DOMAIN.get(comparison.metric) == domain
            and comparison.before.sample_count > 0
            and comparison.before.average is not None
            and comparison.during.sample_count > 0
            and comparison.during.average is not None
        ]
        finding_metrics = [
            finding.metric for finding in findings if finding.evidence_domain == domain
        ]
        if finding_metrics:
            domain_status = "degraded"
        elif evaluated_metrics:
            domain_status = "no_significant_change"
        else:
            domain_status = "unavailable"
        summaries.append(
            DiagnosticEvidenceDomainSummary(
                domain=domain,
                status=domain_status,
                evaluated_metrics=evaluated_metrics,
                finding_metrics=finding_metrics,
            )
        )
    return summaries


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
    findings = _findings(comparisons)
    return DiagnosticWindowComparison(
        window_start=window_start,
        window_end=window_end,
        context_seconds=context_seconds,
        before_start=before_start,
        after_end=after_end,
        metrics=comparisons,
        findings=findings,
        evidence_domains=_evidence_domains(comparisons, findings),
    )
