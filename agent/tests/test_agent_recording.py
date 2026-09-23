from datetime import UTC, datetime, timedelta

from wifi_agent.recording import RecordingStore


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
