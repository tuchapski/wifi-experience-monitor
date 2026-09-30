from datetime import UTC, datetime
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.db.models import (
    AgentRfBssObservation,
    AgentRfScan,
    DiagnosticRecording,
)
from wifi_server.services.recordings import get_recording_rf_scans


def test_get_recording_rf_scans_returns_ordered_snapshots_with_bsses() -> None:
    first_at = datetime(2026, 9, 29, 20, 0, tzinfo=UTC)
    second_at = datetime(2026, 9, 29, 20, 1, tzinfo=UTC)
    first = AgentRfScan(
        id=101,
        agent_id="agt_test",
        recording_id="rec_test",
        scan_id="rfs_1",
        sequence=1,
        observed_at=first_at,
        interface="wlp0s20f3",
        duration_ms=110,
        bss_count=1,
        received_at=first_at,
    )
    second = AgentRfScan(
        id=102,
        agent_id="agt_test",
        recording_id="rec_test",
        scan_id="rfs_2",
        sequence=2,
        observed_at=second_at,
        interface="wlp0s20f3",
        duration_ms=120,
        bss_count=1,
        received_at=second_at,
    )
    first_bss = AgentRfBssObservation(
        rf_scan_id=101,
        bssid="98:7e:ca:8a:3e:0e",
        ssid="AeP",
        frequency_mhz=5805,
        channel=161,
        band="5ghz",
        rssi_dbm=-61,
        associated=True,
        privacy=True,
        security=["RSN"],
        phy_capabilities=["HE"],
    )
    second_bss = AgentRfBssObservation(
        rf_scan_id=102,
        bssid="98:7e:ca:8a:3e:0f",
        ssid="AeP",
        frequency_mhz=2437,
        channel=6,
        band="2.4ghz",
        rssi_dbm=-64,
        associated=True,
        privacy=True,
        security=["RSN"],
        phy_capabilities=["HE"],
    )

    session = Mock(spec=Session)
    session.get.return_value = DiagnosticRecording(id="rec_test")
    session.scalars.return_value.all.side_effect = [
        [second, first],
        [first_bss, second_bss],
    ]

    result = get_recording_rf_scans(session, "rec_test", 2000)

    assert [scan.scan_id for scan in result] == ["rfs_1", "rfs_2"]
    assert result[0].bsses[0].bssid == "98:7e:ca:8a:3e:0e"
    assert result[1].bsses[0].channel == 6


def test_get_recording_rf_scans_returns_empty_when_recording_has_no_scans() -> None:
    session = Mock(spec=Session)
    session.get.return_value = DiagnosticRecording(id="rec_test")
    session.scalars.return_value.all.return_value = []

    assert get_recording_rf_scans(session, "rec_test", 2000) == []
