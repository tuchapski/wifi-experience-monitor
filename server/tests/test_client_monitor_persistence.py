from datetime import UTC
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from test_continuous_detection import NOW, snapshot
from wifi_server.api.agents import router
from wifi_server.config import ServerSettings
from wifi_server.db.base import Base
from wifi_server.db.experience_models import AgentExperienceMonitor
from wifi_server.db.models import Agent, AgentCurrentState
from wifi_server.dependencies import get_session, get_settings
from wifi_server.monitor_schemas import ExperienceProfile, ExperienceProfileUpdate
from wifi_server.schemas import AgentCurrentStateRequest
from wifi_server.services.agents import update_current_state
from wifi_server.services.client_monitor import desired_profile, get_detection, update_profile


@compiles(JSONB, "sqlite")
def _jsonb_as_sqlite_json(_type, _compiler, **_kw):
    return "JSON"


def test_ingestion_persists_rule_state_across_sessions_and_ignores_replays(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'monitor.db'}")
    Base.metadata.create_all(
        engine,
        tables=[Agent.__table__, AgentCurrentState.__table__, AgentExperienceMonitor.__table__],
    )
    with Session(engine) as session:
        agent = Agent(
            id="agt_test",
            name="Test",
            hostname="Test",
            agent_type="sensor",
            status="online",
            agent_version="1",
            first_seen_at=NOW,
            last_seen_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(agent)
        session.commit()
        response = update_profile(
            session, agent.id, ExperienceProfileUpdate(profile=ExperienceProfile(enabled=True))
        )
        version = response.version
        assert desired_profile(session, agent.id)["version"] == version
    for second in (0, 5, 10, 15):
        state = snapshot(second, gateway_latency_ms=100)
        for metadata in state.measurement_metadata.values():
            metadata.profile_version = version
        request = AgentCurrentStateRequest(**state.model_dump(exclude={"agent_id", "updated_at"}))
        with Session(engine) as session, patch("wifi_server.services.agents.datetime") as clock:
            clock.now.return_value = state.observed_at
            update_current_state(
                session, session.get(Agent, "agt_test"), request, monitor_experience=True
            )
    with Session(engine) as session:
        monitor = session.get(AgentExperienceMonitor, "agt_test")
        rule = monitor.detector_state["rules"]["network.gateway_latency_ms"]
        assert rule["status"] == "active"
        assert rule["consecutive_samples"] == 4
        before = monitor.detector_state
        update_current_state(
            session, session.get(Agent, "agt_test"), request, monitor_experience=True
        )
        assert monitor.detector_state == before
        with patch("wifi_server.services.client_monitor.datetime") as clock:
            clock.now.return_value = state.observed_at
            detection = get_detection(
                session, ServerSettings("unused", tmp_path, None, 30, 24), "agt_test"
            )
        assert detection.status == "active"
        assert detection.active_count == 1
        current = session.get(AgentCurrentState, "agt_test")
        assert current.observed_at.replace(tzinfo=UTC) == state.observed_at


def test_detection_and_profile_routes_validate_and_preserve_client_scope(tmp_path):
    from unittest.mock import Mock

    session = Mock(spec=Session)
    agent = Agent(id="agt_test", last_seen_at=NOW)
    session.get.side_effect = lambda model, _id, **kw: (
        agent if model is Agent and _id == "agt_test" else None
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: ServerSettings(
        "unused", tmp_path, None, 30, 24
    )
    with TestClient(app) as client:
        profile = client.get("/api/v1/agents/agt_test/experience/profile")
        assert profile.status_code == 200
        assert profile.json()["profile"]["enabled"] is False
        assert client.get("/api/v1/agents/missing/experience/detection").status_code == 404
        invalid = ExperienceProfile().model_dump()
        invalid["dns_query"] = "--help"
        assert (
            client.put(
                "/api/v1/agents/agt_test/experience/profile", json={"profile": invalid}
            ).status_code
            == 422
        )
        assert (
            client.get("/api/v1/agents/agt_test/experience/detection").json()["status"]
            == "disabled"
        )
