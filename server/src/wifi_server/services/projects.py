"""Create grouped recordings on several Agents with one Server transaction."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.db.analysis_models import RecordingAnalysis
from wifi_server.db.models import Agent, DiagnosticRecording
from wifi_server.db.project_models import (
    DiagnosticProject,
    ProjectAgent,
    ProjectRun,
    ProjectRunRecording,
)
from wifi_server.project_schemas import (
    CreateProjectRequest,
    ProjectAnalysisSummary,
    ProjectFindingResponse,
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
        session.add(
            ProjectAgent(
                project_id=project.id,
                agent_id=agent_id,
                location=request.agent_locations.get(agent_id),
            )
        )
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
    agents: list[tuple[Agent, ProjectAgent]] = []
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
        agents.append((agent, member))

    run = ProjectRun(id=f"run_{uuid4().hex}", project_id=project.id, started_at=now)
    try:
        session.add(run)
        session.flush()
        for agent, member in agents:
            recording = create_recording(
                session,
                agent.id,
                StartRecordingRequest(
                    name=f"{project.name} / {agent.name}"[:255],
                    description=project.objective,
                    site=project.site,
                    location=member.location or project.location,
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
        agent_locations={
            member.agent_id: member.location or project.location for member in members
        },
        created_at=project.created_at,
        runs=[_run_response(session, run) for run in runs],
    )


def _run_response(session: Session, run: ProjectRun) -> ProjectRunResponse:
    members = session.scalars(
        select(ProjectRunRecording)
        .where(ProjectRunRecording.run_id == run.id)
        .order_by(ProjectRunRecording.agent_id)
    ).all()
    member_recordings = [
        (
            member,
            session.get(DiagnosticRecording, member.recording_id)
            if member.recording_id is not None
            else None,
        )
        for member in members
    ]
    recording_ids = [
        member.recording_id
        for member, recording in member_recordings
        if recording is not None
        and recording.status == "completed"
        and recording.sync_status == "complete"
    ]
    analyses = (
        session.scalars(
            select(RecordingAnalysis)
            .where(RecordingAnalysis.recording_id.in_(recording_ids))
            .order_by(
                RecordingAnalysis.recording_id,
                RecordingAnalysis.created_at.desc(),
                RecordingAnalysis.id.desc(),
            )
            .distinct(RecordingAnalysis.recording_id)
        ).all()
        if recording_ids
        else []
    )
    analysis_by_recording = {analysis.recording_id: analysis for analysis in analyses}
    recordings = []
    for member, recording in member_recordings:
        analysis = analysis_by_recording.get(member.recording_id)
        current_analysis = (
            analysis is not None
            and recording is not None
            and recording.status == "completed"
            and recording.sync_status == "complete"
            and analysis.source_metrics_count == recording.metrics_count
            and analysis.source_events_count == recording.events_count
        )
        recordings.append(
            ProjectRecordingResponse(
                agent_id=member.agent_id,
                recording_id=member.recording_id,
                location=recording.location if recording else None,
                status=recording.status if recording else None,
                sync_status=recording.sync_status if recording else None,
                analysis=_analysis_summary(analysis) if current_analysis else None,
            )
        )
    return ProjectRunResponse(
        id=run.id,
        project_id=run.project_id,
        started_at=run.started_at,
        recordings=recordings,
    )


def _analysis_summary(analysis: RecordingAnalysis) -> ProjectAnalysisSummary | None:
    if analysis.status != "complete":
        return None
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    findings = [finding for finding in analysis.findings if isinstance(finding, dict)]
    top_findings = sorted(
        findings,
        key=lambda finding: severity_order.get(str(finding.get("severity")), 3),
    )[:2]
    return ProjectAnalysisSummary(
        engine_version=analysis.engine_version,
        assessment=str(analysis.summary.get("status", "unavailable")),
        evidence_status=str(analysis.summary.get("evidence_status", "unavailable")),
        findings_count=len(findings),
        top_findings=[
            ProjectFindingResponse(
                code=str(finding.get("code", "unknown")),
                severity=str(finding.get("severity", "info")),
                title=str(finding.get("title", "Untitled finding")),
            )
            for finding in top_findings
        ],
    )
