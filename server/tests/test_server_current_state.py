from datetime import UTC, datetime
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.db.models import Agent, AgentCurrentState
from wifi_server.schemas import AgentCurrentStateRequest
from wifi_server.services.agents import update_current_state


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


def test_update_current_state_persists_snapshot() -> None:
    session = Mock(spec=Session)
    session.get.return_value = None
    observed_at = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
    request = AgentCurrentStateRequest(
        observed_at=observed_at,
        wifi={"connected": True, "ssid": "CORP", "rssi_dbm": -53, "tx_mcs": 7},
        network={"ipv4_address": "192.168.1.20", "gateway": "192.168.1.1"},
    )

    response = update_current_state(session, _agent(), request)

    record = session.add.call_args.args[0]
    assert isinstance(record, AgentCurrentState)
    assert record.ssid == "CORP"
    assert record.rssi_dbm == -53
    assert record.raw_state["wifi"]["tx_mcs"] == 7
    assert response.wifi.ssid == "CORP"
    session.commit.assert_called_once()


def test_update_current_state_ignores_older_snapshot() -> None:
    session = Mock(spec=Session)
    current = AgentCurrentState(
        agent_id="agt_test",
        observed_at=datetime(2026, 9, 23, 20, 1, tzinfo=UTC),
        wifi_connected=True,
        interface="wlp0s20f3",
        ssid="CORP",
        bssid=None,
        frequency_mhz=5220,
        channel=44,
        channel_width_mhz=80,
        rssi_dbm=-50,
        snr_db=None,
        tx_rate_mbps=None,
        rx_rate_mbps=None,
        gateway_latency_ms=None,
        dns_latency_ms=None,
        internet_latency_ms=None,
        experience_score=None,
        raw_state={"wifi": {"ssid": "CORP", "rssi_dbm": -50}, "network": {}},
        updated_at=datetime(2026, 9, 23, 20, 1, tzinfo=UTC),
    )
    session.get.return_value = current
    request = AgentCurrentStateRequest(
        observed_at=datetime(2026, 9, 23, 20, 0, tzinfo=UTC),
        wifi={"ssid": "OLD", "rssi_dbm": -80},
    )

    response = update_current_state(session, _agent(), request)

    assert response.wifi.ssid == "CORP"
    session.commit.assert_not_called()
