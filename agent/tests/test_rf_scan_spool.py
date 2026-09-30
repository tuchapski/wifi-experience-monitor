from datetime import UTC, datetime, timedelta

from wifi_agent.core.rf import BssObservation, RfScanResult
from wifi_agent.storage import RfScanSpool


def _result(
    observed_at: datetime,
    *,
    error: str | None = None,
) -> RfScanResult:
    bss = BssObservation(
        bssid="98:7e:ca:8a:3e:0e",
        interface="wlp0s20f3",
        ssid="AeP",
        frequency_mhz=5805,
        channel=161,
        band="5ghz",
        rssi_dbm=-61.0,
        associated=True,
        channel_width_mhz=80,
        security=("RSN",),
        phy_capabilities=("HT", "VHT", "HE"),
    )
    return RfScanResult(
        interface="wlp0s20f3",
        observed_at=observed_at,
        duration_ms=135.5,
        bsses=() if error else (bss,),
        error=error,
    )


def test_rf_scan_spool_persists_sequence_payload_and_acknowledgement(tmp_path) -> None:
    spool = RfScanSpool(tmp_path / "agent.db")
    spool.initialize()
    observed_at = datetime(2026, 9, 29, 20, 0, tzinfo=UTC)

    first = spool.enqueue(_result(observed_at))
    second = spool.enqueue(_result(observed_at + timedelta(minutes=1)))

    assert first is not None
    assert second is not None
    assert first.sequence == 1
    assert second.sequence == 2
    assert spool.pending_count() == 2

    restored = spool.pending()[0]
    assert restored.scan_id == first.scan_id
    assert restored.observed_at == observed_at
    assert restored.interface == "wlp0s20f3"
    assert restored.duration_ms == 135.5
    assert restored.bsses[0]["bssid"] == "98:7e:ca:8a:3e:0e"
    assert restored.bsses[0]["channel"] == 161
    assert restored.bsses[0]["security"] == ["RSN"]
    assert restored.bsses[0]["phy_capabilities"] == ["HT", "VHT", "HE"]

    spool.acknowledge(first.scan_id)

    assert spool.pending_count() == 1
    assert spool.pending()[0].scan_id == second.scan_id


def test_rf_scan_spool_does_not_enqueue_failed_scan(tmp_path) -> None:
    spool = RfScanSpool(tmp_path / "agent.db")
    spool.initialize()
    observed_at = datetime(2026, 9, 29, 20, 0, tzinfo=UTC)

    queued = spool.enqueue(_result(observed_at, error="iw scan failed: Operation not permitted"))

    assert queued is None
    assert spool.pending_count() == 0


def test_rf_scan_spool_prunes_old_unsynchronized_scans(tmp_path) -> None:
    spool = RfScanSpool(tmp_path / "agent.db")
    spool.initialize()
    observed_at = datetime(2026, 9, 29, 20, 0, tzinfo=UTC)

    first = spool.enqueue(_result(observed_at))
    assert first is not None

    cutoff = first.created_at + timedelta(seconds=1)
    assert spool.prune_before(cutoff) == 1
    assert spool.pending_count() == 0
