from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session
from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent
from wifi_server.schemas import RenameAgentRequest
from wifi_server.services.agents import rename_agent


def _settings() -> ServerSettings:
    return ServerSettings(
        database_url="postgresql+psycopg://unused",
        recording_storage_root=Path("/tmp"),
        enrollment_token=None,
        agent_offline_after_seconds=15,
        telemetry_retention_hours=24,
    )


def test_rename_updates_display_name_without_changing_agent_identity() -> None:
    now = datetime.now(UTC)
    agent = Agent(
        id="agt_test",
        name="old-name",
        hostname="laptop-01",
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
    session = Mock(spec=Session)
    session.get.return_value = agent
    session.scalars.return_value.all.return_value = []

    response = rename_agent(
        session,
        _settings(),
        "agt_test",
        RenameAgentRequest(name=" sensor-local-01 "),
    )

    assert response.id == agent.id == "agt_test"
    assert response.name == agent.name == "sensor-local-01"
    assert agent.hostname == "laptop-01"
    session.commit.assert_called_once()


def test_rename_rejects_unknown_agent_and_blank_name() -> None:
    session = Mock(spec=Session)
    session.get.return_value = None

    with pytest.raises(HTTPException) as missing:
        rename_agent(session, _settings(), "absent", RenameAgentRequest(name="new-name"))
    assert missing.value.status_code == 404
    session.commit.assert_not_called()

    with pytest.raises(ValidationError):
        RenameAgentRequest(name="   ")
