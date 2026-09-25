"""Temporal correlation of diagnostic findings with recorded state changes."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.db.recording_models import RecordingEvent
from wifi_server.recording_schemas import (
    CorrelatedRecordingEvent,
    DiagnosticEvidenceCorrelation,
)
from wifi_server.services.diagnostic_windows import compare_diagnostic_window


def _correlated_event(
    event: RecordingEvent,
    window_start: datetime,
    window_end: datetime,
) -> CorrelatedRecordingEvent:
    if event.observed_at < window_start:
        phase = "before"
        distance_seconds = (window_start - event.observed_at).total_seconds()
    elif event.observed_at > window_end:
        phase = "after"
        distance_seconds = (event.observed_at - window_end).total_seconds()
    else:
        phase = "during"
        distance_seconds = 0.0

    return CorrelatedRecordingEvent(
        observed_at=event.observed_at,
        event_type=event.event_type,
        severity=event.severity,
        phase=phase,
        distance_seconds=distance_seconds,
        seconds_from_window_start=(event.observed_at - window_start).total_seconds(),
        data=event.data,
    )


def correlate_diagnostic_evidence(
    session: Session,
    recording_id: str,
    metrics: list[str],
    window_start: datetime,
    window_end: datetime,
    context_seconds: int,
) -> DiagnosticEvidenceCorrelation:
    """Return findings and nearby state changes without assigning causality."""
    comparison = compare_diagnostic_window(
        session,
        recording_id,
        metrics,
        window_start,
        window_end,
        context_seconds,
    )

    events = list(
        session.scalars(
            select(RecordingEvent)
            .where(
                RecordingEvent.recording_id == recording_id,
                RecordingEvent.event_type == "state.changed",
                RecordingEvent.observed_at >= comparison.before_start,
                RecordingEvent.observed_at <= comparison.after_end,
            )
            .order_by(RecordingEvent.observed_at)
        ).all()
    )

    return DiagnosticEvidenceCorrelation(
        window_start=window_start,
        window_end=window_end,
        context_seconds=context_seconds,
        findings=comparison.findings,
        events=[_correlated_event(event, window_start, window_end) for event in events],
    )
