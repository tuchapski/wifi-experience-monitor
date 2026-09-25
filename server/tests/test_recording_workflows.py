"""Project membership and automatic analysis behavior for finished recordings."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from wifi_server.api.recordings import recording_manifest
from wifi_server.db.models import Agent, DiagnosticRecording
from wifi_server.recording_schemas import RecordingManifestRequest, RecordingManifestResponse
from wifi_server.services.analyses import ensure_recording_analysis
from wifi_server.services.recordings import get_recording, list_recordings


def _recording(recording_id: str) -> DiagnosticRecording:
    now = datetime.now(UTC)
    return DiagnosticRecording(
        id=recording_id,
        agent_id="agt_test",
        name=recording_id,
        description=None,
        status="completed",
        sync_status="complete",
        profile_id="wifi-deep-dive",
        max_duration_minutes=30,
        started_at=now,
        ended_at=now,
        site=None,
        location=None,
        agent_version="0.1.0",
        schema_version=1,
        metrics_count=3,
        events_count=1,
        tests_count=0,
        artifacts_count=0,
        created_at=now,
        updated_at=now,
    )


def test_agent_recordings_identify_project_membership() -> None:
    session = Mock(spec=Session)
    session.get.return_value = Mock(spec=Agent)
    individual = _recording("rec_individual")
    project = _recording("rec_project")
    session.execute.return_value.all.return_value = [
        (individual, None, None, None),
        (project, "prj_test", "Office Wi-Fi", "run_test"),
    ]

    recordings = list_recordings(session, "agt_test")

    assert recordings[0].project_run_id is None
    assert recordings[1].project_id == "prj_test"
    assert recordings[1].project_name == "Office Wi-Fi"
    assert recordings[1].project_run_id == "run_test"

    session.execute.return_value.one_or_none.return_value = (
        project,
        "prj_test",
        "Office Wi-Fi",
        "run_test",
    )
    assert get_recording(session, "rec_project").project_run_id == "run_test"


def test_automatic_analysis_runs_only_for_new_complete_dataset() -> None:
    session = Mock(spec=Session)
    recording = _recording("rec_test")
    session.get.return_value = recording
    session.scalar.return_value = None

    with patch("wifi_server.services.analyses.run_recording_analysis") as analyze:
        ensure_recording_analysis(session, recording.id)
        analyze.assert_called_once_with(session, recording.id)

        session.scalar.return_value = "ana_existing"
        ensure_recording_analysis(session, recording.id)
        analyze.assert_called_once()

        recording.sync_status = "incomplete"
        session.scalar.return_value = None
        ensure_recording_analysis(session, recording.id)
        analyze.assert_called_once()


def test_manifest_schedules_analysis_only_after_complete_sync() -> None:
    session = Mock(spec=Session)
    recording = _recording("rec_test")
    session.get.return_value = recording
    payload = RecordingManifestRequest(
        ended_at=datetime.now(UTC), batches_count=0, metrics_count=0, events_count=0
    )

    with (
        patch("wifi_server.api.recordings.authenticate_agent"),
        patch("wifi_server.api.recordings.finalize_manifest") as finalize,
    ):
        for sync_status, expected_tasks in (("incomplete", 0), ("complete", 1)):
            finalize.return_value = RecordingManifestResponse(
                recording_id=recording.id,
                status="completed",
                sync_status=sync_status,
                missing_sequences=[],
            )
            tasks = BackgroundTasks()
            recording_manifest(recording.id, payload, tasks, session, "Bearer test-token")
            assert len(tasks.tasks) == expected_tasks
