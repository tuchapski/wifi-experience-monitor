from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent, AgentRfBssObservation, AgentRfScan
from wifi_server.schemas import RfScanRequest
from wifi_server.services.agents import ingest_rf_scan


def _settings(tmp_path) -> ServerSettings:
    return ServerSettings(
        database_url="postgresql+psycopg://unused",
        recording_storage_root=tmp_path,
        enrollment_token="test",
        agent_offline_after_seconds=15,
        telemetry_retention_hours=24,
        rf_scan_retention_hours=168,
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
        agent_version="1.0.0",
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )


def _request(scan_id: str = "rfs_one", sequence: int = 1) -> RfScanRequest:
    return RfScanRequest(
        scan_id=scan_id,
        sequence=sequence,
        observed_at="2026-09-29T20:00:10Z",
        interface="wlp0s20f3",
        duration_ms=132.5,
        bsses=[
            {
                "bssid": "98:7e:ca:8a:3e:0e",
                "ssid": "AeP",
                "frequency_mhz": 5805,
                "channel": 161,
                "band": "5ghz",
                "rssi_dbm": -61,
                "associated": True,
                "channel_width_mhz": 80,
                "privacy": True,
                "security": ["RSN"],
                "phy_capabilities": ["HT", "VHT", "HE"],
            }
        ],
    )


def test_ingest_rf_scan_persists_scan_and_bss_rows(tmp_path) -> None:
    session = Mock(spec=Session)
    session.scalar.side_effect = [None, None]

    def assign_scan_id() -> None:
        added = [call.args[0] for call in session.add.call_args_list]
        scan = next(item for item in added if isinstance(item, AgentRfScan))
        scan.id = 123

    session.flush.side_effect = assign_scan_id

    response = ingest_rf_scan(session, _settings(tmp_path), _agent(), _request())

    added = [call.args[0] for call in session.add.call_args_list]
    scan = next(item for item in added if isinstance(item, AgentRfScan))
    bss = next(item for item in added if isinstance(item, AgentRfBssObservation))

    assert scan.scan_id == "rfs_one"
    assert scan.bss_count == 1
    assert bss.rf_scan_id == 123
    assert bss.bssid == "98:7e:ca:8a:3e:0e"
    assert bss.channel == 161
    assert bss.phy_capabilities == ["HT", "VHT", "HE"]
    assert response.status == "accepted"
    assert response.bsses_received == 1
    session.commit.assert_called_once()


def test_ingest_rf_scan_is_idempotent(tmp_path) -> None:
    session = Mock(spec=Session)
    session.scalar.return_value = AgentRfScan(
        agent_id="agt_test",
        scan_id="rfs_one",
        sequence=1,
        observed_at=datetime.now(UTC),
        interface="wlp0s20f3",
        duration_ms=100,
        bss_count=7,
        received_at=datetime.now(UTC),
    )

    response = ingest_rf_scan(session, _settings(tmp_path), _agent(), _request())

    assert response.status == "already_accepted"
    assert response.bsses_received == 7
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_ingest_rf_scan_rejects_sequence_reuse(tmp_path) -> None:
    session = Mock(spec=Session)
    session.scalar.side_effect = [
        None,
        AgentRfScan(
            agent_id="agt_test",
            scan_id="rfs_other",
            sequence=1,
            observed_at=datetime.now(UTC),
            interface="wlp0s20f3",
            duration_ms=100,
            bss_count=1,
            received_at=datetime.now(UTC),
        ),
    ]

    with pytest.raises(HTTPException) as exc_info:
        ingest_rf_scan(session, _settings(tmp_path), _agent(), _request())

    assert exc_info.value.status_code == 409
