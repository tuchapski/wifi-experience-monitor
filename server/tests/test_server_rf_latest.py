from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from wifi_server.db.models import Agent, AgentRfBssObservation, AgentRfScan
from wifi_server.services.agents import get_latest_rf_scan


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
        agent_version="1.0.0",
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )


def test_get_latest_rf_scan_returns_bss_inventory() -> None:
    observed_at = datetime(2026, 9, 29, 20, 0, tzinfo=UTC)
    scan = AgentRfScan(
        id=123,
        agent_id="agt_test",
        scan_id="rfs_latest",
        sequence=7,
        observed_at=observed_at,
        interface="wlp0s20f3",
        duration_ms=121.5,
        bss_count=2,
        received_at=observed_at,
    )
    associated = AgentRfBssObservation(
        rf_scan_id=123,
        bssid="98:7e:ca:8a:3e:0e",
        ssid="AeP",
        frequency_mhz=5805,
        channel=161,
        band="5ghz",
        rssi_dbm=-61,
        associated=True,
        privacy=True,
        security=["RSN"],
        phy_capabilities=["HT", "VHT", "HE"],
    )
    neighbor = AgentRfBssObservation(
        rf_scan_id=123,
        bssid="86:7e:ca:8a:3e:0e",
        ssid="AeP",
        frequency_mhz=5805,
        channel=161,
        band="5ghz",
        rssi_dbm=-68,
        associated=False,
        privacy=True,
        security=["RSN"],
        phy_capabilities=["HT", "VHT", "HE"],
    )

    session = Mock(spec=Session)
    session.get.return_value = _agent()
    session.scalar.return_value = scan
    session.scalars.return_value.all.return_value = [associated, neighbor]

    response = get_latest_rf_scan(session, "agt_test")

    assert response.scan_id == "rfs_latest"
    assert response.sequence == 7
    assert len(response.bsses) == 2
    assert response.bsses[0].associated is True
    assert response.bsses[0].channel == 161
    assert response.bsses[1].rssi_dbm == -68


def test_get_latest_rf_scan_returns_404_when_no_scan_exists() -> None:
    session = Mock(spec=Session)
    session.get.return_value = _agent()
    session.scalar.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_latest_rf_scan(session, "agt_test")

    assert exc_info.value.status_code == 404
    assert "RF scan" in str(exc_info.value.detail)


def test_get_latest_rf_scan_returns_404_for_unknown_agent() -> None:
    session = Mock(spec=Session)
    session.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_latest_rf_scan(session, "agt_missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Agent not found"
