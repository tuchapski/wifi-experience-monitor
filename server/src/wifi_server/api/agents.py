from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.dependencies import get_session, get_settings
from wifi_server.schemas import (
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
from wifi_server.services.agents import (
    authenticate_agent,
    enroll_agent,
    get_agent,
    get_agent_telemetry,
    get_current_state,
    ingest_telemetry_batch,
    list_agents,
    process_heartbeat,
    update_current_state,
)
from wifi_server.services.recordings import get_pending_commands

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected Bearer agent token",
        )
    return token


@router.post("/enroll", response_model=AgentEnrollmentResponse, status_code=201)
def enroll(
    payload: AgentEnrollmentRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> AgentEnrollmentResponse:
    return enroll_agent(session, settings, payload)


@router.post("/{agent_id}/heartbeat", response_model=AgentHeartbeatResponse)
def heartbeat(
    agent_id: str,
    payload: AgentHeartbeatRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> AgentHeartbeatResponse:
    token = _bearer_token(authorization)
    agent = authenticate_agent(session, agent_id, token)
    remote_address = request.client.host if request.client else None
    response = process_heartbeat(session, settings, agent, payload, remote_address)
    commands = get_pending_commands(session, agent.id, datetime.now(UTC))
    session.commit()
    return response.model_copy(update={"commands": commands})


@router.get("", response_model=list[AgentResponse])
def agents(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> list[AgentResponse]:
    return list_agents(session, settings)


@router.put("/{agent_id}/state", response_model=AgentCurrentStateResponse)
def publish_state(
    agent_id: str,
    payload: AgentCurrentStateRequest,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> AgentCurrentStateResponse:
    token = _bearer_token(authorization)
    agent = authenticate_agent(session, agent_id, token)
    return update_current_state(session, agent, payload)


@router.get("/{agent_id}/state", response_model=AgentCurrentStateResponse)
def current_state(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> AgentCurrentStateResponse:
    return get_current_state(session, agent_id)


@router.post(
    "/{agent_id}/telemetry/batches",
    response_model=TelemetryBatchResponse,
)
def publish_telemetry_batch(
    agent_id: str,
    payload: TelemetryBatchRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> TelemetryBatchResponse:
    token = _bearer_token(authorization)
    agent = authenticate_agent(session, agent_id, token)
    return ingest_telemetry_batch(session, settings, agent, payload)


@router.get(
    "/{agent_id}/telemetry",
    response_model=list[TelemetryPointResponse],
)
def telemetry(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    metric: Annotated[str | None, Query(max_length=128)] = None,
    hours: Annotated[float, Query(gt=0, le=24)] = 1,
    limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
) -> list[TelemetryPointResponse]:
    since = datetime.now(UTC) - timedelta(hours=hours)
    return get_agent_telemetry(session, agent_id, metric, since, limit)


@router.get("/{agent_id}", response_model=AgentResponse)
def agent(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> AgentResponse:
    return get_agent(session, settings, agent_id)
