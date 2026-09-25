from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from wifi_server.analysis.current_link import score_link
from wifi_server.config import ServerSettings
from wifi_server.db.models import (
    Agent,
    AgentCapability,
    AgentCredential,
    AgentCurrentState,
    AgentSession,
    AgentTelemetry,
    AgentTelemetryBatch,
)
from wifi_server.schemas import (
    AgentCapabilityResponse,
    AgentCurrentStateRequest,
    AgentCurrentStateResponse,
    AgentEnrollmentRequest,
    AgentEnrollmentResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentResponse,
    TelemetryBatchRequest,
    TelemetryBatchResponse,
    TelemetryPointResponse,
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


def update_current_state(
    session: Session,
    agent: Agent,
    request: AgentCurrentStateRequest,
) -> AgentCurrentStateResponse:
    current = session.get(AgentCurrentState, agent.id)
    if current is not None and request.observed_at <= current.observed_at:
        return _current_state_response(current)

    now = datetime.now(UTC)
    raw_state = request.model_dump(
        mode="json",
        exclude={"observed_at"},
        exclude_none=True,
    )
    wifi = request.wifi
    network = request.network
    link_score = score_link(wifi.model_dump(exclude_none=True), request.collector_errors)
    raw_state["wifi"]["link_score"] = link_score

    if current is None:
        current = AgentCurrentState(
            agent_id=agent.id,
            observed_at=request.observed_at,
            raw_state=raw_state,
            updated_at=now,
        )
        session.add(current)

    current.observed_at = request.observed_at
    current.wifi_connected = wifi.connected
    current.interface = wifi.interface
    current.ssid = wifi.ssid
    current.bssid = wifi.bssid
    current.frequency_mhz = wifi.frequency_mhz
    current.channel = wifi.channel
    current.channel_width_mhz = wifi.channel_width_mhz
    current.rssi_dbm = wifi.rssi_dbm
    current.snr_db = wifi.snr_db
    current.tx_rate_mbps = wifi.tx_rate_mbps
    current.rx_rate_mbps = wifi.rx_rate_mbps
    current.gateway_latency_ms = network.gateway_latency_ms
    current.dns_latency_ms = network.dns_latency_ms
    current.internet_latency_ms = network.internet_latency_ms
    current.experience_score = None  # Wi-Fi link quality is not end-to-end experience.
    current.raw_state = raw_state
    current.updated_at = now

    session.commit()
    return _current_state_response(current)


def get_current_state(
    session: Session,
    agent_id: str,
) -> AgentCurrentStateResponse:
    if session.get(Agent, agent_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    current = session.get(AgentCurrentState, agent_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current state is not available for this agent",
        )
    return _current_state_response(current)


def _current_state_response(current: AgentCurrentState) -> AgentCurrentStateResponse:
    raw_state = current.raw_state or {}
    return AgentCurrentStateResponse(
        agent_id=current.agent_id,
        observed_at=current.observed_at,
        updated_at=current.updated_at,
        wifi=raw_state.get("wifi", {}),
        network=raw_state.get("network", {}),
        collector_errors=raw_state.get("collector_errors", []),
    )


def ingest_telemetry_batch(
    session: Session,
    settings: ServerSettings,
    agent: Agent,
    request: TelemetryBatchRequest,
) -> TelemetryBatchResponse:
    existing = session.scalar(
        select(AgentTelemetryBatch).where(
            AgentTelemetryBatch.agent_id == agent.id,
            AgentTelemetryBatch.batch_id == request.batch_id,
        )
    )
    if existing is not None:
        return TelemetryBatchResponse(
            batch_id=existing.batch_id,
            sequence=existing.sequence,
            status="already_accepted",
            items_received=existing.item_count,
        )

    sequence_owner = session.scalar(
        select(AgentTelemetryBatch).where(
            AgentTelemetryBatch.agent_id == agent.id,
            AgentTelemetryBatch.sequence == request.sequence,
        )
    )
    if sequence_owner is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telemetry sequence already belongs to another batch",
        )

    now = datetime.now(UTC)
    session.add(
        AgentTelemetryBatch(
            agent_id=agent.id,
            batch_id=request.batch_id,
            sequence=request.sequence,
            item_count=len(request.items),
            received_at=now,
        )
    )
    for item in request.items:
        session.add(
            AgentTelemetry(
                agent_id=agent.id,
                observed_at=item.observed_at,
                metric=item.metric,
                value=item.value,
                min_value=item.min_value,
                max_value=item.max_value,
                sample_count=item.sample_count,
                unit=item.unit,
                labels=item.labels,
                received_at=now,
            )
        )

    cutoff = now - timedelta(hours=settings.telemetry_retention_hours)
    session.execute(delete(AgentTelemetry).where(AgentTelemetry.observed_at < cutoff))
    session.execute(delete(AgentTelemetryBatch).where(AgentTelemetryBatch.received_at < cutoff))
    session.commit()

    return TelemetryBatchResponse(
        batch_id=request.batch_id,
        sequence=request.sequence,
        status="accepted",
        items_received=len(request.items),
    )


def get_agent_telemetry(
    session: Session,
    agent_id: str,
    metric: str | None,
    since: datetime,
    limit: int,
) -> list[TelemetryPointResponse]:
    if session.get(Agent, agent_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    query = select(AgentTelemetry).where(
        AgentTelemetry.agent_id == agent_id,
        AgentTelemetry.observed_at >= since,
    )
    if metric:
        query = query.where(AgentTelemetry.metric == metric)
    records = list(
        session.scalars(query.order_by(AgentTelemetry.observed_at.desc()).limit(limit)).all()
    )
    records.reverse()

    return [
        TelemetryPointResponse(
            observed_at=record.observed_at,
            metric=record.metric,
            value=record.value,
            min_value=record.min_value,
            max_value=record.max_value,
            sample_count=record.sample_count,
            unit=record.unit,
            labels=record.labels,
            received_at=record.received_at,
        )
        for record in records
    ]
