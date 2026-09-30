from datetime import UTC, datetime
from unittest.mock import Mock

from wifi_agent.cli import _service_rf_scan
from wifi_agent.config import AgentSettings
from wifi_agent.core.rf import BssObservation, RfScanResult
from wifi_agent.runtime.rf_sync import RfScanSyncEngine
from wifi_agent.storage import AgentIdentity, RfScanSpool


def _result() -> RfScanResult:
    return RfScanResult(
        interface="wlp0s20f3",
        observed_at=datetime(2026, 9, 29, 20, 0, tzinfo=UTC),
        duration_ms=110,
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


def _identity() -> AgentIdentity:
    return AgentIdentity(
        agent_id="agt_test",
        agent_token="secret",
        server_url="http://127.0.0.1:8000",
        enrolled_at=datetime(2026, 9, 29, 19, 0, tzinfo=UTC),
    )


def test_rf_scan_service_enqueues_completed_scan_and_starts_next_due_scan() -> None:
    runtime = Mock()
    runtime.interface = "wlp0s20f3"
    runtime.poll.return_value = _result()
    spool = Mock()
    spool.enqueue.return_value = Mock(scan_id="rfs_test", sequence=1)

    _service_rf_scan(runtime, spool, 100.0)

    spool.enqueue.assert_called_once_with(runtime.poll.return_value)
    runtime.maybe_start.assert_called_once_with(100.0)


def test_rf_scan_sync_acknowledges_accepted_scan(tmp_path) -> None:
    spool = RfScanSpool(tmp_path / "agent.db")
    spool.initialize()
    queued = spool.enqueue(_result())
    assert queued is not None

    engine = RfScanSyncEngine(Mock(spec=AgentSettings), _identity(), spool)
    engine.client = Mock()
    engine.client.publish_rf_scan.return_value = {
        "scan_id": queued.scan_id,
        "sequence": queued.sequence,
        "status": "accepted",
        "bsses_received": 1,
    }

    assert engine.sync_pending() == 1
    assert spool.pending_count() == 0


def test_rf_scan_sync_keeps_scan_when_server_is_unreachable(tmp_path) -> None:
    spool = RfScanSpool(tmp_path / "agent.db")
    spool.initialize()
    spool.enqueue(_result())

    engine = RfScanSyncEngine(Mock(spec=AgentSettings), _identity(), spool)
    engine.client = Mock()
    engine.client.publish_rf_scan.side_effect = OSError("server unavailable")

    assert engine.sync_pending() == 0
    assert spool.pending_count() == 1
