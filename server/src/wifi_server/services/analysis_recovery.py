"""Resume automatic analyses for recordings left without current findings."""

import logging
from threading import Event, Thread

from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.analysis import ENGINE_VERSION
from wifi_server.db.analysis_models import RecordingAnalysis
from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.session import ServerDatabase
from wifi_server.dependencies import get_database
from wifi_server.services.analyses import ensure_recording_analysis

logger = logging.getLogger(__name__)
SCAN_INTERVAL_SECONDS = 30
BATCH_SIZE = 10


def missing_analysis_ids(session: Session, after_id: str | None = None) -> list[str]:
    """Page through completed recordings without an analysis for their current dataset."""
    existing = (
        select(RecordingAnalysis.id)
        .where(
            RecordingAnalysis.recording_id == DiagnosticRecording.id,
            RecordingAnalysis.engine_version == ENGINE_VERSION,
            RecordingAnalysis.status == "complete",
            RecordingAnalysis.source_metrics_count == DiagnosticRecording.metrics_count,
            RecordingAnalysis.source_events_count == DiagnosticRecording.events_count,
        )
        .exists()
    )
    query = (
        select(DiagnosticRecording.id)
        .where(
            DiagnosticRecording.status == "completed",
            DiagnosticRecording.sync_status == "complete",
            ~existing,
        )
        .order_by(DiagnosticRecording.id)
        .limit(BATCH_SIZE)
    )
    if after_id is not None:
        query = query.where(DiagnosticRecording.id > after_id)
    return list(session.scalars(query).all())


def recover_pending_analyses(database: ServerDatabase, after_id: str | None) -> str | None:
    """Try one page, allowing an individual failure to leave other recordings available."""
    with database.session() as session:
        recording_ids = missing_analysis_ids(session, after_id)
        if not recording_ids and after_id is not None:
            recording_ids = missing_analysis_ids(session)

    for recording_id in recording_ids:
        try:
            with database.session() as session:
                ensure_recording_analysis(session, recording_id)
        except Exception:
            logger.exception("Automatic analysis recovery failed for recording %s", recording_id)

    return recording_ids[-1] if recording_ids else None


def _recovery_loop(stop: Event) -> None:
    cursor: str | None = None
    while not stop.is_set():
        try:
            cursor = recover_pending_analyses(get_database(), cursor)
        except Exception:
            logger.exception("Automatic analysis recovery scan failed")
        stop.wait(SCAN_INTERVAL_SECONDS)


def start_analysis_recovery() -> tuple[Event, Thread]:
    """Start a bounded background scan; the first scan runs immediately."""
    stop = Event()
    thread = Thread(target=_recovery_loop, args=(stop,), daemon=True, name="analysis-recovery")
    thread.start()
    return stop, thread
