from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wifi_server.analysis import ENGINE_VERSION, analyze_recording
from wifi_server.analysis.recording import MetricSample, StateEvent
from wifi_server.analysis_schemas import RecordingAnalysisResponse
from wifi_server.db.analysis_models import RecordingAnalysis
from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.recording_models import RecordingEvent, RecordingMetric


def run_recording_analysis(
    session: Session,
    recording_id: str,
) -> RecordingAnalysisResponse:
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    if recording.status != "completed" or recording.sync_status != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recording analysis requires a completed and fully synchronized dataset",
        )

    metric_rows = list(
        session.scalars(
            select(RecordingMetric)
            .where(RecordingMetric.recording_id == recording_id)
            .order_by(RecordingMetric.observed_at)
        ).all()
    )
    event_rows = list(
        session.scalars(
            select(RecordingEvent)
            .where(RecordingEvent.recording_id == recording_id)
            .order_by(RecordingEvent.observed_at)
        ).all()
    )
    result = analyze_recording(
        [
            MetricSample(
                observed_at=row.observed_at,
                metric=row.metric,
                value=row.value,
                labels=row.labels,
            )
            for row in metric_rows
        ],
        [
            StateEvent(
                observed_at=row.observed_at,
                event_type=row.event_type,
                data=row.data,
            )
            for row in event_rows
        ],
        started_at=recording.started_at,
        ended_at=recording.ended_at,
    )

    analysis = RecordingAnalysis(
        id=f"ana_{uuid4().hex}",
        recording_id=recording_id,
        engine_version=ENGINE_VERSION,
        status="complete",
        source_metrics_count=len(metric_rows),
        source_events_count=len(event_rows),
        summary=result.summary,
        findings=result.findings,
        policy=result.policy,
        created_at=datetime.now(UTC),
    )
    session.add(analysis)
    session.commit()
    return _response(analysis)


def ensure_recording_analysis(session: Session, recording_id: str) -> None:
    """Create the current analysis once after a complete manifest is accepted."""
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:recording_id))"),
        {"recording_id": recording_id},
    )
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None or recording.status != "completed" or recording.sync_status != "complete":
        return

    existing = session.scalar(
        select(RecordingAnalysis.id).where(
            RecordingAnalysis.recording_id == recording_id,
            RecordingAnalysis.engine_version == ENGINE_VERSION,
            RecordingAnalysis.status == "complete",
            RecordingAnalysis.source_metrics_count == recording.metrics_count,
            RecordingAnalysis.source_events_count == recording.events_count,
        )
    )
    if existing is None:
        run_recording_analysis(session, recording_id)


def get_latest_recording_analysis(
    session: Session,
    recording_id: str,
) -> RecordingAnalysisResponse:
    if session.get(DiagnosticRecording, recording_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    analysis = session.scalar(
        select(RecordingAnalysis)
        .where(RecordingAnalysis.recording_id == recording_id)
        .order_by(RecordingAnalysis.created_at.desc())
        .limit(1)
    )
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording analysis is not available",
        )
    return _response(analysis)


def _response(analysis: RecordingAnalysis) -> RecordingAnalysisResponse:
    return RecordingAnalysisResponse(
        id=analysis.id,
        recording_id=analysis.recording_id,
        engine_version=analysis.engine_version,
        status=analysis.status,
        source_metrics_count=analysis.source_metrics_count,
        source_events_count=analysis.source_events_count,
        summary=analysis.summary,
        findings=analysis.findings,
        policy=analysis.policy,
        created_at=analysis.created_at,
    )
