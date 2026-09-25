from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session
from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent
from wifi_server.db.project_models import DiagnosticProject, ProjectAgent, ProjectRunRecording
from wifi_server.project_schemas import CreateProjectRequest
from wifi_server.recording_schemas import StartRecordingRequest
from wifi_server.services.projects import create_project, start_project_run
from wifi_server.services.recordings import create_recording


def _settings() -> ServerSettings:
    return ServerSettings(
        database_url="postgresql+psycopg://unused",
        recording_storage_root=Path("/tmp"),
        enrollment_token=None,
        agent_offline_after_seconds=15,
        telemetry_retention_hours=24,
    )


def _agent(agent_id: str) -> Agent:
    now = datetime.now(UTC)
    return Agent(
        id=agent_id,
        name=agent_id,
        hostname=agent_id,
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


def _project() -> DiagnosticProject:
    return DiagnosticProject(
        id="prj_test",
        name="Office Wi-Fi",
        objective="Investigate roaming",
        site="HQ",
        location="Floor 3",
        profile_id="wifi-deep-dive",
        max_duration_minutes=30,
        created_at=datetime.now(UTC),
    )


def test_project_requires_unique_agent_ids_and_nonblank_name() -> None:
    for payload in (
        {"name": "Project", "agent_ids": ["agt_1", "agt_1"]},
        {"name": "  ", "agent_ids": ["agt_1"]},
        {"name": "Project", "agent_ids": []},
        {"name": "Project", "agent_ids": ["agt_1"], "agent_locations": {"agt_2": "Lobby"}},
        {"name": "Project", "agent_ids": ["agt_1"], "agent_locations": {"agt_1": "x" * 256}},
    ):
        with pytest.raises(ValidationError):
            CreateProjectRequest.model_validate(payload)


def test_project_persists_selected_agent_positions() -> None:
    session = Mock(spec=Session)
    session.get.return_value = _agent("agt_1")
    request = CreateProjectRequest(
        name="Office",
        location="Floor 3",
        agent_ids=["agt_1", "agt_2"],
        agent_locations={"agt_1": " West lounge ", "agt_2": " "},
    )

    with patch("wifi_server.services.projects._project_response"):
        create_project(session, request)

    members = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], ProjectAgent)
    ]
    assert {member.agent_id: member.location for member in members} == {
        "agt_1": "West lounge",
        "agt_2": None,
    }
    session.commit.assert_called_once()


def test_recording_can_be_queued_without_individual_commit() -> None:
    session = Mock(spec=Session)
    session.get.return_value = _agent("agt_1")
    session.scalar.return_value = None

    result = create_recording(
        session, "agt_1", StartRecordingRequest(name="Office Wi-Fi"), commit=False
    )

    assert result.status == "created"
    session.commit.assert_not_called()
    assert session.add.call_count == 2


def test_run_queues_one_recording_per_agent_and_commits_once() -> None:
    session = Mock(spec=Session)
    project = _project()
    agents = {agent_id: _agent(agent_id) for agent_id in ("agt_1", "agt_2")}

    def get_record(model: type, key: str) -> object:
        if model is DiagnosticProject:
            return project
        if model is Agent:
            return agents[key]
        return Mock(
            status="created",
            sync_status="pending",
            location="West lounge" if key == "rec_agt_1" else "Floor 3",
        )

    session.get.side_effect = get_record
    members = [
        ProjectAgent(
            project_id="prj_test",
            agent_id=agent_id,
            location="West lounge" if agent_id == "agt_1" else None,
        )
        for agent_id in agents
    ]
    linked = [
        ProjectRunRecording(run_id="run_test", agent_id=agent_id, recording_id=f"rec_{agent_id}")
        for agent_id in agents
    ]
    session.scalars.return_value.all.side_effect = [members, linked]

    with patch("wifi_server.services.projects.create_recording") as queue:
        queue.side_effect = [Mock(id="rec_agt_1"), Mock(id="rec_agt_2")]
        result = start_project_run(session, _settings(), "prj_test")

    assert {item.agent_id for item in result.recordings} == set(agents)
    assert {item.recording_id for item in result.recordings} == {"rec_agt_1", "rec_agt_2"}
    assert queue.call_count == 2
    assert all(call.kwargs["commit"] is False for call in queue.call_args_list)
    links = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], ProjectRunRecording)
    ]
    assert {item.recording_id for item in links} == {"rec_agt_1", "rec_agt_2"}
    assert all(call.args[2].max_duration_minutes == 30 for call in queue.call_args_list)
    assert [call.args[2].location for call in queue.call_args_list] == ["West lounge", "Floor 3"]
    assert {item.agent_id: item.location for item in result.recordings} == {
        "agt_1": "West lounge",
        "agt_2": "Floor 3",
    }
    session.commit.assert_called_once()


def test_failed_second_agent_rolls_back_both_queued_commands() -> None:
    session = Mock(spec=Session)
    project = _project()
    agents = {agent_id: _agent(agent_id) for agent_id in ("agt_1", "agt_2")}

    def get_record(model: type, key: str) -> object:
        if model is DiagnosticProject:
            return project
        return agents[key]

    session.get.side_effect = get_record
    session.scalars.return_value.all.return_value = [
        ProjectAgent(project_id="prj_test", agent_id=agent_id) for agent_id in agents
    ]

    with patch("wifi_server.services.projects.create_recording") as queue:
        queue.side_effect = [Mock(id="rec_agt_1"), HTTPException(status_code=409, detail="busy")]
        with pytest.raises(HTTPException) as failure:
            start_project_run(session, _settings(), "prj_test")

    assert failure.value.status_code == 409
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_offline_member_prevents_queuing_any_commands() -> None:
    session = Mock(spec=Session)
    project = _project()
    offline = _agent("agt_1")
    offline.status = "offline"
    session.get.side_effect = lambda model, key: project if model is DiagnosticProject else offline
    session.scalars.return_value.all.return_value = [
        ProjectAgent(project_id="prj_test", agent_id="agt_1")
    ]

    with patch("wifi_server.services.projects.create_recording") as queue:
        with pytest.raises(HTTPException) as failure:
            start_project_run(session, _settings(), "prj_test")

    assert failure.value.status_code == 409
    queue.assert_not_called()
    session.commit.assert_not_called()
