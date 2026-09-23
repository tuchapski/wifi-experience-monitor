from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent, AgentCapability, AgentCredential, AgentSession
from wifi_server.schemas import (
    AgentCapabilityResponse,
    AgentEnrollmentRequest,
    AgentEnrollmentResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentResponse,
)
from wifi_server.security import hash_agent_token, issue_agent_token


def is_agent_online(
    last_seen_at: datetime,
    now: datetime,
    offline_after_seconds: float,
) -> bool:
    return now - last_seen_at <= timedelta(seconds=offline_after_seconds)


def enroll_agent(
    session: Session,
    settings: ServerSettings,
    request: AgentEnrollmentRequest,
) -> AgentEnrollmentResponse:
    if settings.enrollment_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent enrollment is not configured on this server",
        )
    if not compare_digest(request.enrollment_token, settings.enrollment_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid enrollment token",
        )

    now = datetime.now(UTC)
    agent_id = f"agt_{uuid4().hex}"
    agent_token = issue_agent_token()
    agent = Agent(
        id=agent_id,
        name=request.name,
        hostname=request.hostname,
        agent_type=request.agent_type,
        status="offline",
        os_name=request.os_name,
        os_version=request.os_version,
        agent_version=request.agent_version,
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(agent)
    session.add(
        AgentCredential(
            agent_id=agent_id,
            token_hash=hash_agent_token(agent_token),
            created_at=now,
            revoked_at=None,
        )
    )

    seen_capabilities: set[str] = set()
    for capability in request.capabilities:
        if capability.capability in seen_capabilities:
            continue
        seen_capabilities.add(capability.capability)
        session.add(
            AgentCapability(
                agent_id=agent_id,
                capability=capability.capability,
                enabled=capability.enabled,
                capability_metadata=capability.metadata,
                detected_at=now,
            )
        )

    session.commit()
    return AgentEnrollmentResponse(
        agent_id=agent_id,
        agent_token=agent_token,
        config_revision=0,
        enrolled_at=now,
    )


def authenticate_agent(session: Session, agent_id: str, token: str) -> Agent:
    token_hash = hash_agent_token(token)
    credential = session.scalar(
        select(AgentCredential).where(
            AgentCredential.agent_id == agent_id,
            AgentCredential.token_hash == token_hash,
            AgentCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )

    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


def process_heartbeat(
    session: Session,
    settings: ServerSettings,
    agent: Agent,
    request: AgentHeartbeatRequest,
    remote_address: str | None,
) -> AgentHeartbeatResponse:
    now = datetime.now(UTC)
    previous_last_seen = agent.last_seen_at
    gap_exceeded = not is_agent_online(
        previous_last_seen,
        now,
        settings.agent_offline_after_seconds,
    )

    open_session = session.scalar(
        select(AgentSession)
        .where(
            AgentSession.agent_id == agent.id,
            AgentSession.disconnected_at.is_(None),
        )
        .order_by(AgentSession.connected_at.desc())
        .limit(1)
    )

    if open_session is not None and gap_exceeded:
        open_session.disconnected_at = previous_last_seen
        open_session.disconnect_reason = "heartbeat_timeout"
        open_session = None

    if open_session is None:
        session.add(
            AgentSession(
                agent_id=agent.id,
                connected_at=now,
                disconnected_at=None,
                agent_version=request.agent_version,
                remote_address=remote_address,
                disconnect_reason=None,
            )
        )

    agent.status = "online"
    agent.agent_version = request.agent_version
    agent.last_seen_at = now
    agent.updated_at = now
    session.commit()

    return AgentHeartbeatResponse(
        server_time=now,
        desired_config_revision=request.config_revision,
        commands=[],
    )


def list_agents(session: Session, settings: ServerSettings) -> list[AgentResponse]:
    agents = session.scalars(select(Agent).order_by(Agent.name)).all()
    now = datetime.now(UTC)
    return [_agent_response(session, settings, agent, now) for agent in agents]


def get_agent(session: Session, settings: ServerSettings, agent_id: str) -> AgentResponse:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return _agent_response(session, settings, agent, datetime.now(UTC))


def _agent_response(
    session: Session,
    settings: ServerSettings,
    agent: Agent,
    now: datetime,
) -> AgentResponse:
    capabilities = session.scalars(
        select(AgentCapability)
        .where(AgentCapability.agent_id == agent.id)
        .order_by(AgentCapability.capability)
    ).all()
    effective_status = (
        "online"
        if agent.status == "online"
        and is_agent_online(agent.last_seen_at, now, settings.agent_offline_after_seconds)
        else "offline"
    )

    return AgentResponse(
        id=agent.id,
        name=agent.name,
        hostname=agent.hostname,
        agent_type=agent.agent_type,
        status=effective_status,
        os_name=agent.os_name,
        os_version=agent.os_version,
        agent_version=agent.agent_version,
        first_seen_at=agent.first_seen_at,
        last_seen_at=agent.last_seen_at,
        capabilities=[
            AgentCapabilityResponse(
                capability=capability.capability,
                enabled=capability.enabled,
                metadata=capability.capability_metadata,
            )
            for capability in capabilities
        ],
    )
