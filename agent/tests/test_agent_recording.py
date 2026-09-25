import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from wifi_agent.config import AgentSettings
from wifi_agent.recording import RecordingStore
from wifi_agent.recording.controller import RecordingController
from wifi_agent.storage import AgentIdentity


def test_recording_store_persists_batches_and_manifest_state(tmp_path) -> None:
    store = RecordingStore(tmp_path / "agent.db")
    store.initialize()
    started_at = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    recording = store.start("rec_test", started_at)

    assert recording.recording_id == "rec_test"
    assert recording.status == "recording"

    first = store.enqueue(
        "rec_test",
        metrics=[
            {
                "observed_at": started_at.isoformat(),
                "metric": "wifi.rssi_dbm",
                "value": -55.0,
                "unit": "dBm",
                "labels": {},
            }
        ],
        events=[],
        created_at=started_at,
    )
    second = store.enqueue(
        "rec_test",
        metrics=[],
        events=[
            {
                "observed_at": (started_at + timedelta(seconds=1)).isoformat(),
                "event_type": "state.changed",
                "severity": "info",
                "data": {"metric": "wifi.bssid"},
            }
        ],
        created_at=started_at + timedelta(seconds=1),
    )

    assert first is not None and first.sequence == 1
    assert second is not None and second.sequence == 2
    assert store.pending_batch_count() == 2

    store.acknowledge_batch(first.batch_id)
    assert store.pending_batch_count() == 1

    completed = store.stop("rec_test", started_at + timedelta(seconds=10))
    assert completed.status == "completed"
    assert completed.metrics_count == 1
    assert completed.events_count == 1
    assert completed.batches_count == 2
    assert completed.manifest_pending is True

    store.acknowledge_batch(second.batch_id)
    assert store.has_pending_batches("rec_test") is False
    assert len(store.recordings_waiting_for_manifest()) == 1

    store.acknowledge_manifest("rec_test")
    assert store.recordings_waiting_for_manifest() == []


def test_recording_marks_empty_collection_cycle(tmp_path) -> None:
    settings = AgentSettings.from_environment()
    identity = AgentIdentity("agent_test", "token", settings.server_url, datetime.now(UTC))
    controller = RecordingController(settings, identity, tmp_path / "agent.db")
    at = datetime.now(UTC)
    controller.store.start("rec_cycle", at - timedelta(seconds=1))

    controller.consume([], observed_at=at, collector_errors=["survey unavailable"])

    batch = controller.store.pending()[0]
    assert len(batch.metrics) == 1
    assert batch.metrics[0]["metric"] == "sensor.collection_cycle"
    assert batch.metrics[0]["labels"] == {
        "configured_interval_seconds": settings.telemetry_sample_interval_seconds,
        "collector_errors_count": 1,
    }


def test_autonomous_recording_stops_after_restart_and_queues_manifest(tmp_path) -> None:
    settings = AgentSettings.from_environment()
    identity = AgentIdentity("agent_test", "token", settings.server_url, datetime.now(UTC))
    path = tmp_path / "agent.db"
    controller = RecordingController(settings, identity, path)
    controller.client.acknowledge_command = Mock()
    controller._start("cmd_start", {"recording_id": "rec_timed", "max_duration_minutes": 15})
    recording = controller.store.active()
    assert recording is not None
    assert recording.deadline_at == recording.started_at + timedelta(minutes=15)

    restarted = RecordingController(settings, identity, path)
    assert restarted.stop_if_due(recording.deadline_at - timedelta(seconds=1)) is False
    assert restarted.stop_if_due(recording.deadline_at) is True
    assert restarted.stop_if_due(recording.deadline_at + timedelta(minutes=1)) is False
    completed = restarted.store.get("rec_timed")
    assert completed is not None
    assert completed.ended_at == recording.deadline_at
    assert completed.manifest_pending is True
    assert len(restarted.store.recordings_waiting_for_manifest()) == 1


def test_recording_rejects_invalid_duration_before_start(tmp_path) -> None:
    settings = AgentSettings.from_environment()
    identity = AgentIdentity("agent_test", "token", settings.server_url, datetime.now(UTC))
    controller = RecordingController(settings, identity, tmp_path / "agent.db")
    for duration in (0, 1441, True, "60"):
        try:
            controller._start(
                "cmd_start", {"recording_id": "rec_bad", "max_duration_minutes": duration}
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid duration was accepted: {duration!r}")
    assert controller.store.active() is None


def test_recording_store_adds_deadline_column_to_existing_database(tmp_path) -> None:
    path = tmp_path / "agent.db"
    legacy_start = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE diagnostic_recordings_local (
                recording_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                started_at TEXT NOT NULL, ended_at TEXT, next_sequence INTEGER NOT NULL,
                metrics_count INTEGER NOT NULL, events_count INTEGER NOT NULL,
                manifest_pending INTEGER NOT NULL DEFAULT 0
            )"""
        )
        connection.execute(
            """INSERT INTO diagnostic_recordings_local (
                recording_id, status, started_at, next_sequence, metrics_count, events_count
            ) VALUES (?, 'completed', ?, 1, 0, 0)""",
            ("rec_legacy", legacy_start.isoformat()),
        )
    store = RecordingStore(path)
    store.initialize()
    legacy = store.get("rec_legacy")
    assert legacy is not None
    assert legacy.deadline_at is None
    recording = store.start("rec_existing", datetime.now(UTC), max_duration_minutes=60)
    assert recording.deadline_at == recording.started_at + timedelta(hours=1)
