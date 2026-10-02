import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import httpx
import pytest
from wifi_agent.config import AgentSettings
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.recording.controller import RecordingController
from wifi_agent.recording.store import RecordingStore
from wifi_agent.storage import AgentIdentity

NOW = datetime(2026, 10, 2, 18, tzinfo=UTC)
VERSION = "exp_" + "a" * 32


def controller(tmp_path):
    settings = AgentSettings.from_environment()
    result = RecordingController(
        settings,
        AgentIdentity("agt_test", "secret", settings.server_url, NOW),
        tmp_path / "agent.db",
    )
    result.client = Mock()
    result.configure_capture(
        {
            "version": VERSION,
            "profile": {
                "enabled": True,
                "automatic_capture": True,
                "capture_pre_seconds": 120,
                "confirm_seconds": 15,
            },
        }
    )
    return result


def command(mode="automatic", recording_id="rec_test"):
    return {
        "id": "cmd_test",
        "type": "recording.capture",
        "payload": {
            "recording_id": recording_id,
            "profile_version": VERSION,
            "mode": mode,
            "window_start": (NOW - timedelta(seconds=10)).isoformat(),
            "window_end": (NOW + timedelta(seconds=30)).isoformat(),
        },
    }


def cycle(instance, second):
    # Repeated cached measurements preserve original clocks and are deduplicated.
    instance.consume(
        [
            Observation(
                source="synthetic",
                kind=ObservationKind.GAUGE,
                metric="network.gateway_latency_ms",
                value=100,
                observed_at=NOW - timedelta(seconds=10),
                metadata={"profile_version": VERSION, "sample_count": 4},
            ),
            Observation(
                source="wifi",
                kind=ObservationKind.STATE,
                metric="wifi.connected",
                value=True,
                observed_at=NOW + timedelta(seconds=second),
            ),
        ],
        observed_at=NOW + timedelta(seconds=second),
    )


def test_durable_buffer_atomic_export_ack_retry_and_local_deadline(tmp_path):
    instance = controller(tmp_path)
    cycle(instance, -10)
    cycle(instance, -5)
    assert instance.store.active() is None
    instance = controller(tmp_path)  # Agent restart preserves pre-trigger evidence.
    with patch("wifi_agent.recording.controller.datetime", wraps=datetime) as clock:
        clock.now.return_value = NOW
        instance.client.acknowledge_command.side_effect = httpx.ConnectError("offline")
        with pytest.raises(httpx.ConnectError):
            instance.handle_commands([command()])
    batches_before = instance.store.pending_batch_count()
    assert batches_before == 2
    assert instance.store.active().deadline_at == NOW + timedelta(seconds=30)
    instance.store.stop("rec_test", NOW + timedelta(seconds=30))
    restarted = controller(tmp_path)
    with patch("wifi_agent.recording.controller.datetime", wraps=datetime) as clock:
        clock.now.return_value = NOW + timedelta(seconds=60)
        restarted.handle_commands([command()])  # Retry after expiry and completion is journaled.
    assert restarted.store.active() is None
    assert restarted.store.pending_batch_count() == batches_before
    metrics = [item for batch in restarted.store.pending() for item in batch.metrics]
    assert sum(item["metric"] == "network.gateway_latency_ms" for item in metrics) == 1
    assert (
        next(item for item in metrics if item["metric"] == "network.gateway_latency_ms")["labels"][
            "measurement"
        ]["sample_count"]
        == 4
    )
    assert restarted.client.acknowledge_command.call_args.kwargs["data"]["buffer_cycles"] == 2


def test_reusing_manual_preserves_deadline_and_deduplicates_live_evidence(tmp_path):
    instance = controller(tmp_path)
    manual = instance.store.start("rec_manual", NOW - timedelta(seconds=10), 20)
    cycle(instance, -10)
    cycle(instance, -5)
    before = instance.store.get("rec_manual")
    with patch("wifi_agent.recording.controller.datetime", wraps=datetime) as clock:
        clock.now.return_value = NOW
        instance.handle_commands([command("reused", "rec_manual")])
    after = instance.store.get("rec_manual")
    assert after.metrics_count == before.metrics_count
    assert after.events_count == before.events_count
    assert after.deadline_at == manual.deadline_at
    assert after.started_at == manual.started_at
    assert instance.stop_if_due(NOW + timedelta(seconds=31)) is False


def test_conflicting_or_expired_commands_cannot_start_another_recording(tmp_path):
    instance = controller(tmp_path)
    instance.store.start("rec_manual", NOW)
    with patch("wifi_agent.recording.controller.datetime", wraps=datetime) as clock:
        clock.now.return_value = NOW
        instance.handle_commands([command()])
    assert instance.client.acknowledge_command.call_args.kwargs["status"] == "failed"
    assert instance.store.active().recording_id == "rec_manual"
    instance.store.stop("rec_manual", NOW)
    with patch("wifi_agent.recording.controller.datetime", wraps=datetime) as clock:
        clock.now.return_value = NOW + timedelta(seconds=60)
        instance.handle_commands([command()])
    assert instance.store.get("rec_test") is None
    assert instance.store.active() is None


def test_buffer_limits_context_isolation_and_disabling(tmp_path):
    instance = controller(tmp_path)
    store = instance.store
    payload = [
        {
            "observed_at": NOW.isoformat(),
            "metric": "test",
            "value": 1,
            "labels": {"blob": "x" * 900000},
        }
    ]
    for second in range(25):
        store.buffer_cycle("old", payload, [], NOW + timedelta(seconds=second), 300)
    with sqlite3.connect(store.database_path) as connection:
        count, size = connection.execute(
            "SELECT COUNT(*), SUM(payload_bytes) FROM experience_buffer"
        ).fetchone()
        assert count <= 2000 and size <= 16 * 1024 * 1024
    store.buffer_cycle("new", [], [], NOW + timedelta(seconds=26), 300)
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM experience_buffer").fetchone()[0] == 1
    instance.configure_capture(None)
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM experience_buffer").fetchone()[0] == 0
    assert store.active() is None


def test_export_rolls_back_if_any_buffered_cycle_is_invalid(tmp_path):
    store = RecordingStore(tmp_path / "agent.db")
    store.initialize()
    store.buffer_cycle("scope", [{"metric": "test"}], [], NOW, 120)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "INSERT INTO experience_buffer VALUES (?, ?, ?, ?)",
            ((NOW + timedelta(seconds=1)).isoformat(), "scope", "invalid-json", 12),
        )
    with pytest.raises(ValueError):
        store.capture(
            "cmd_test",
            "rec_test",
            "scope",
            NOW,
            NOW + timedelta(seconds=30),
            NOW + timedelta(seconds=2),
            "automatic",
        )
    assert store.get("rec_test") is None
    assert store.pending_batch_count() == 0
