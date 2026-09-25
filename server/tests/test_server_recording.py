from datetime import UTC, datetime
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.db.models import Agent, DiagnosticRecording
from wifi_server.db.recording_models import (
    AgentCommand,
    RecordingBatch,
    RecordingEvent,
    RecordingMetric,
)
from wifi_server.recording_schemas import (
    AgentCommandAckRequest,
    RecordingBatchRequest,
    StartRecordingRequest,
)
from wifi_server.services.recordings import (
    acknowledge_command,
    create_recording,
    get_recording_events,
    get_recording_metrics,
    ingest_recording_batch,
)


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
    assert command.payload["max_duration_minutes"] == 60
    assert response.max_duration_minutes == 60
    session.commit.assert_called_once()


def test_delayed_start_ack_does_not_reopen_recording() -> None:
    now = datetime.now(UTC)
    for status in ("stopping", "completed"):
        recording = DiagnosticRecording(
            id="rec_delayed", status=status, started_at=None, updated_at=now
        )
        command = AgentCommand(
            id="cmd_delayed",
            command_type="recording.start",
            payload={"recording_id": recording.id},
            status="delivered",
            created_at=now,
            result={},
        )
        session = Mock(spec=Session)
        session.get.return_value = recording

        acknowledge_command(
            session,
            command,
            AgentCommandAckRequest(status="acked", data={"started_at": now.isoformat()}),
        )

        assert recording.status == status
        assert recording.started_at == now
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


def test_recording_metric_and_event_queries_map_persisted_data() -> None:
    now = datetime.now(UTC)
    recording = Mock(spec=DiagnosticRecording)
    metric = RecordingMetric(
        recording_id="rec_test",
        observed_at=now,
        metric="wifi.rssi_dbm",
        value=-57,
        unit="dBm",
        labels={"interface": "wlp0s20f3"},
        received_at=now,
    )
    event = RecordingEvent(
        recording_id="rec_test",
        observed_at=now,
        event_type="state.changed",
        severity="info",
        data={
            "metric": "wifi.channel",
            "previous": 36,
            "current": 44,
        },
        received_at=now,
    )
    session = Mock(spec=Session)
    session.get.return_value = recording
    session.scalars.return_value.all.side_effect = [[metric], [event]]

    metrics = get_recording_metrics(
        session,
        "rec_test",
        "wifi.rssi_dbm",
        100,
    )
    events = get_recording_events(session, "rec_test", 100)

    assert len(metrics) == 1
    assert metrics[0].metric == "wifi.rssi_dbm"
    assert metrics[0].value == -57
    assert len(events) == 1
    assert events[0].event_type == "state.changed"
    assert events[0].data["current"] == 44
