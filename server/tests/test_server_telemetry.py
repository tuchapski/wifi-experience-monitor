from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent, AgentTelemetry, AgentTelemetryBatch
from wifi_server.schemas import TelemetryBatchRequest
from wifi_server.services.agents import ingest_telemetry_batch


def _settings(tmp_path) -> ServerSettings:
    return ServerSettings(
        database_url="postgresql+psycopg://unused",
        recording_storage_root=tmp_path,
        enrollment_token="test",
        agent_offline_after_seconds=15,
        telemetry_retention_hours=24,
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
        agent_version="0.1.0",
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )


def _request(batch_id: str = "tb_one", sequence: int = 1) -> TelemetryBatchRequest:
    return TelemetryBatchRequest(
        batch_id=batch_id,
        sequence=sequence,
        items=[
            {
                "observed_at": "2026-09-23T20:00:10Z",
                "metric": "wifi.rssi_dbm",
                "value": -52,
                "min_value": -55,
                "max_value": -50,
                "sample_count": 10,
                "unit": "dBm",
                "labels": {"interface": "wlp0s20f3"},
            }
        ],
    )


def test_ingest_telemetry_batch_persists_receipt_and_items(tmp_path) -> None:
    session = Mock(spec=Session)
    session.scalar.side_effect = [None, None]

    response = ingest_telemetry_batch(session, _settings(tmp_path), _agent(), _request())

    added = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(item, AgentTelemetryBatch) for item in added)
    assert any(isinstance(item, AgentTelemetry) for item in added)
    assert response.status == "accepted"
    assert response.items_received == 1
    session.commit.assert_called_once()


def test_ingest_telemetry_batch_is_idempotent(tmp_path) -> None:
    session = Mock(spec=Session)
    session.scalar.return_value = AgentTelemetryBatch(
        agent_id="agt_test",
        batch_id="tb_one",
        sequence=1,
        item_count=1,
        received_at=datetime.now(UTC),
    )

    response = ingest_telemetry_batch(session, _settings(tmp_path), _agent(), _request())

    assert response.status == "already_accepted"
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_ingest_telemetry_rejects_sequence_reuse(tmp_path) -> None:
    session = Mock(spec=Session)
    session.scalar.side_effect = [
        None,
        AgentTelemetryBatch(
            agent_id="agt_test",
            batch_id="tb_other",
            sequence=1,
            item_count=1,
            received_at=datetime.now(UTC),
        ),
    ]

    with pytest.raises(HTTPException) as exc_info:
        ingest_telemetry_batch(session, _settings(tmp_path), _agent(), _request())

    assert exc_info.value.status_code == 409
