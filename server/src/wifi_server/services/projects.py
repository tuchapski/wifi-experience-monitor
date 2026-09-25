"""Create grouped recordings on several Agents with one Server transaction."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent, DiagnosticRecording
from wifi_server.db.project_models import (
    DiagnosticProject,
    ProjectAgent,
    ProjectRun,
    ProjectRunRecording,
)
from wifi_server.project_schemas import (
    CreateProjectRequest,
    ProjectRecordingResponse,
    ProjectResponse,
    ProjectRunResponse,
)
from wifi_server.recording_schemas import StartRecordingRequest
from wifi_server.services.agents import is_agent_online
from wifi_server.services.recordings import create_recording


def create_project(session: Session, request: CreateProjectRequest) -> ProjectResponse:
    for agent_id in request.agent_ids:
        if session.get(Agent, agent_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

    project = DiagnosticProject(
        id=f"prj_{uuid4().hex}",
        name=request.name,
        objective=request.objective,
        site=request.site,
        location=request.location,
        profile_id=request.profile_id,
        max_duration_minutes=request.max_duration_minutes,
        created_at=datetime.now(UTC),
    )
    session.add(project)
    session.flush()
    for agent_id in request.agent_ids:
        session.add(ProjectAgent(project_id=project.id, agent_id=agent_id))
    session.commit()
    return _project_response(session, project)


def list_projects(session: Session) -> list[ProjectResponse]:
    projects = session.scalars(
        select(DiagnosticProject).order_by(DiagnosticProject.created_at.desc())
    ).all()
    return [_project_response(session, project) for project in projects]


def start_project_run(
    session: Session, settings: ServerSettings, project_id: str
) -> ProjectRunResponse:
    project = session.get(DiagnosticProject, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    members = session.scalars(
        select(ProjectAgent)
        .where(ProjectAgent.project_id == project.id)
        .order_by(ProjectAgent.agent_id)
    ).all()
    if not members:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project has no Agents")

    now = datetime.now(UTC)
    agents: list[Agent] = []
    for member in members:
        agent = session.get(Agent, member.agent_id)
        if (
            agent is None
            or agent.status != "online"
            or not is_agent_online(agent.last_seen_at, now, settings.agent_offline_after_seconds)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent {member.agent_id} is offline or unavailable",
            )
        agents.append(agent)

    run = ProjectRun(id=f"run_{uuid4().hex}", project_id=project.id, started_at=now)
    try:
        session.add(run)
        session.flush()
        for agent in agents:
            recording = create_recording(
                session,
                agent.id,
                StartRecordingRequest(
                    name=f"{project.name} / {agent.name}"[:255],
                    description=project.objective,
                    site=project.site,
                    location=project.location,
                    profile_id=project.profile_id,
                    max_duration_minutes=project.max_duration_minutes,
                ),
                commit=False,
            )
            session.flush()
            session.add(
                ProjectRunRecording(run_id=run.id, agent_id=agent.id, recording_id=recording.id)
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _run_response(session, run)


def _project_response(session: Session, project: DiagnosticProject) -> ProjectResponse:
    members = session.scalars(
        select(ProjectAgent)
        .where(ProjectAgent.project_id == project.id)
        .order_by(ProjectAgent.agent_id)
    ).all()
    runs = session.scalars(
        select(ProjectRun)
        .where(ProjectRun.project_id == project.id)
        .order_by(ProjectRun.started_at.desc())
    ).all()
    return ProjectResponse(
        id=project.id,
        name=project.name,
        objective=project.objective,
        site=project.site,
        location=project.location,
        profile_id=project.profile_id,
        max_duration_minutes=project.max_duration_minutes,
        agent_ids=[member.agent_id for member in members],
        created_at=project.created_at,
        runs=[_run_response(session, run) for run in runs],
    )


def _run_response(session: Session, run: ProjectRun) -> ProjectRunResponse:
    members = session.scalars(
        select(ProjectRunRecording)
        .where(ProjectRunRecording.run_id == run.id)
        .order_by(ProjectRunRecording.agent_id)
    ).all()
    recordings = []
    for member in members:
        recording = (
            session.get(DiagnosticRecording, member.recording_id)
            if member.recording_id is not None
            else None
        )
        recordings.append(
            ProjectRecordingResponse(
                agent_id=member.agent_id,
                recording_id=member.recording_id,
                status=recording.status if recording else None,
                sync_status=recording.sync_status if recording else None,
            )
        )
    return ProjectRunResponse(
        id=run.id,
        project_id=run.project_id,
        started_at=run.started_at,
        recordings=recordings,
    )
