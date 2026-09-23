from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
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
)
from wifi_server.services.agents import (
    authenticate_agent,
    enroll_agent,
    get_agent,
    get_current_state,
    list_agents,
    process_heartbeat,
    update_current_state,
)

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
    return process_heartbeat(session, settings, agent, payload, remote_address)


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


@router.get("/{agent_id}", response_model=AgentResponse)
def agent(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> AgentResponse:
    return get_agent(session, settings, agent_id)
