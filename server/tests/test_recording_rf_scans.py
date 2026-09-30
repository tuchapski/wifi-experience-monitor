from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent, AgentRfBssObservation, AgentRfScan, DiagnosticRecording
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


def _request(recording_id: str | None = "rec_test") -> RfScanRequest:
    return RfScanRequest(
        scan_id="rfs_recorded",
        sequence=10,
        recording_id=recording_id,
        observed_at="2026-09-29T21:00:00Z",
        interface="wlp0s20f3",
        duration_ms=125,
        bsses=[
            {
                "bssid": "98:7e:ca:8a:3e:0e",
                "ssid": "AeP",
                "frequency_mhz": 5805,
                "channel": 161,
                "band": "5ghz",
                "rssi_dbm": -61,
                "associated": True,
            }
        ],
    )


def test_recording_rf_scan_is_linked_to_same_agent_recording(tmp_path) -> None:
    recording = DiagnosticRecording(id="rec_test", agent_id="agt_test")
    session = Mock(spec=Session)
    session.scalar.side_effect = [None, None]
    session.get.return_value = recording

    def assign_scan_id() -> None:
        scan = next(
            call.args[0]
            for call in session.add.call_args_list
            if isinstance(call.args[0], AgentRfScan)
        )
        scan.id = 321

    session.flush.side_effect = assign_scan_id

    response = ingest_rf_scan(session, _settings(tmp_path), _agent(), _request())

    added = [call.args[0] for call in session.add.call_args_list]
    scan = next(item for item in added if isinstance(item, AgentRfScan))
    bss = next(item for item in added if isinstance(item, AgentRfBssObservation))

    assert scan.recording_id == "rec_test"
    assert bss.rf_scan_id == 321
    assert response.status == "accepted"
    session.commit.assert_called_once()


def test_recording_rf_scan_rejects_recording_from_another_agent(tmp_path) -> None:
    session = Mock(spec=Session)
    session.scalar.return_value = None
    session.get.return_value = DiagnosticRecording(id="rec_other", agent_id="agt_other")

    with pytest.raises(HTTPException) as exc_info:
        ingest_rf_scan(session, _settings(tmp_path), _agent(), _request("rec_other"))

    assert exc_info.value.status_code == 409
    session.commit.assert_not_called()


def test_recording_association_must_match_idempotent_replay(tmp_path) -> None:
    existing = AgentRfScan(
        agent_id="agt_test",
        recording_id="rec_original",
        scan_id="rfs_recorded",
        sequence=10,
        observed_at=datetime.now(UTC),
        interface="wlp0s20f3",
        duration_ms=100,
        bss_count=1,
        received_at=datetime.now(UTC),
    )
    session = Mock(spec=Session)
    session.scalar.return_value = existing

    with pytest.raises(HTTPException) as exc_info:
        ingest_rf_scan(session, _settings(tmp_path), _agent(), _request("rec_other"))

    assert exc_info.value.status_code == 409
