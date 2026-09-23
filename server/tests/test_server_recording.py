from datetime import UTC, datetime
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.db.models import Agent, DiagnosticRecording
from wifi_server.db.recording_models import AgentCommand, RecordingBatch, RecordingMetric
from wifi_server.recording_schemas import RecordingBatchRequest, StartRecordingRequest
from wifi_server.services.recordings import create_recording, ingest_recording_batch


def _agent() -> Agent:
    now = datetime.now(UTC)
    return Agent(
        id="agt_test",
        name="sensor-test",
        hostname="sensor-test",
        agent_type="sensor",
        status="online",
        os_name="Ubuntu",
        os_version="24.04",
        agent_version="0.1.0",
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )


def test_create_recording_queues_start_command() -> None:
    session = Mock(spec=Session)
    session.get.return_value = _agent()
    session.scalar.return_value = None

    response = create_recording(
        session,
        "agt_test",
        StartRecordingRequest(name="Office issue"),
    )

    added = [call.args[0] for call in session.add.call_args_list]
    recording = next(item for item in added if isinstance(item, DiagnosticRecording))
    command = next(item for item in added if isinstance(item, AgentCommand))
    assert response.id == recording.id
    assert response.status == "created"
    assert command.command_type == "recording.start"
    assert command.payload["recording_id"] == recording.id
    session.commit.assert_called_once()


def test_recording_batch_persists_raw_metric() -> None:
    now = datetime.now(UTC)
    recording = DiagnosticRecording(
        id="rec_test",
        agent_id="agt_test",
        name="Test",
        description=None,
        status="recording",
        sync_status="pending",
        profile_id="wifi-deep-dive",
        started_at=now,
        ended_at=None,
        site=None,
        location=None,
        agent_version="0.1.0",
        schema_version=1,
        metrics_count=0,
        events_count=0,
        tests_count=0,
        artifacts_count=0,
        created_at=now,
        updated_at=now,
    )
    session = Mock(spec=Session)
    session.scalar.side_effect = [None, None]
    request = RecordingBatchRequest(
        batch_id="rb_one",
        sequence=1,
        metrics=[
            {
                "observed_at": "2026-09-23T22:00:00Z",
                "metric": "wifi.rssi_dbm",
                "value": -55,
                "unit": "dBm",
                "labels": {"interface": "wlp0s20f3"},
            }
        ],
    )

    response = ingest_recording_batch(session, recording, request)

    added = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(item, RecordingBatch) for item in added)
    assert any(isinstance(item, RecordingMetric) for item in added)
    assert response.status == "accepted"
    assert recording.metrics_count == 1
    assert recording.sync_status == "syncing"
