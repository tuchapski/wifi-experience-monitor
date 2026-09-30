from concurrent.futures import Future
from datetime import UTC, datetime, timedelta

from wifi_agent.core.rf import BssObservation, RfScanResult
from wifi_agent.recording.context import set_active_recording_id
from wifi_agent.runtime.rf_scan import RfScanRuntime
from wifi_agent.storage import RfScanSpool


def _result(observed_at: datetime) -> RfScanResult:
    return RfScanResult(
        interface="wlp0s20f3",
        observed_at=observed_at,
        duration_ms=100,
        bsses=(
            BssObservation(
                bssid="98:7e:ca:8a:3e:0e",
                interface="wlp0s20f3",
                ssid="AeP",
                frequency_mhz=5805,
                channel=161,
                band="5ghz",
                rssi_dbm=-61,
                associated=True,
            ),
        ),
    )


def test_runtime_snapshots_recording_context_when_scan_starts() -> None:
    runtime = RfScanRuntime("wlp0s20f3", interval_seconds=60, timeout_seconds=15)
    pending: Future[RfScanResult] = Future()
    runtime._executor.submit = lambda *args, **kwargs: pending  # type: ignore[method-assign]
    observed_at = datetime(2026, 9, 29, 21, 0, tzinfo=UTC)

    set_active_recording_id("rec_test")
    try:
        assert runtime.maybe_start(100) is True
        set_active_recording_id(None)
        pending.set_result(_result(observed_at))
        completed = runtime.poll()
        assert completed is not None
        assert completed.recording_id == "rec_test"
    finally:
        set_active_recording_id(None)
        runtime.close()


def test_rf_spool_preserves_recording_scan_from_rolling_prune(tmp_path) -> None:
    spool = RfScanSpool(tmp_path / "agent.db")
    spool.initialize()
    observed_at = datetime(2026, 9, 29, 21, 0, tzinfo=UTC)

    rolling = spool.enqueue(_result(observed_at))
    recorded = spool.enqueue(
        RfScanResult(
            interface="wlp0s20f3",
            observed_at=observed_at + timedelta(seconds=1),
            duration_ms=100,
            bsses=_result(observed_at).bsses,
            recording_id="rec_test",
        )
    )

    assert rolling is not None
    assert recorded is not None
    assert recorded.recording_id == "rec_test"
    assert recorded.to_payload()["recording_id"] == "rec_test"

    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    assert spool.prune_before(cutoff) == 1

    pending = spool.pending()
    assert len(pending) == 1
    assert pending[0].scan_id == recorded.scan_id
    assert pending[0].recording_id == "rec_test"
