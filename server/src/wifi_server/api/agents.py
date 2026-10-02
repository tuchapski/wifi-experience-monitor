from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent
from wifi_server.dependencies import get_session, get_settings
from wifi_server.episode_schemas import ClientEpisodePage, ClientEpisodeResponse
from wifi_server.experience_schemas import ClientExperienceResponse
from wifi_server.monitor_schemas import (
    ClientDetectionResponse,
    ExperienceProfileResponse,
    ExperienceProfileUpdate,
)
from wifi_server.schemas import (
    AgentCurrentStateRequest,
    AgentCurrentStateResponse,
    AgentEnrollmentRequest,
    AgentEnrollmentResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentResponse,
    RenameAgentRequest,
    RfLatestScanResponse,
    RfScanRequest,
    RfScanResponse,
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
    get_latest_rf_scan,
    ingest_rf_scan,
    ingest_telemetry_batch,
    list_agents,
    process_heartbeat,
    rename_agent,
    update_current_state,
)
from wifi_server.services.client_experience import get_client_experience
from wifi_server.services.client_monitor import (
    desired_profile,
    get_detection,
    get_profile,
    update_profile,
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
    session.get(Agent, agent.id, with_for_update=True)
    commands = get_pending_commands(session, agent.id, datetime.now(UTC))
    session.commit()
    return response.model_copy(
        update={"commands": commands, "experience_profile": desired_profile(session, agent.id)}
    )


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
    session.get(Agent, agent.id, with_for_update=True)
    return update_current_state(session, agent, payload, monitor_experience=True)


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


@router.get("/{agent_id}/experience", response_model=ClientExperienceResponse)
def client_experience(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> ClientExperienceResponse:
    return get_client_experience(session, settings, agent_id)


@router.get("/{agent_id}/experience/profile", response_model=ExperienceProfileResponse)
def experience_profile(
    agent_id: str, session: Annotated[Session, Depends(get_session)]
) -> ExperienceProfileResponse:
    return get_profile(session, agent_id)


@router.put("/{agent_id}/experience/profile", response_model=ExperienceProfileResponse)
def save_experience_profile(
    agent_id: str,
    payload: ExperienceProfileUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ExperienceProfileResponse:
    return update_profile(session, agent_id, payload, track_episodes=True)


@router.get("/{agent_id}/experience/detection", response_model=ClientDetectionResponse)
def client_detection(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> ClientDetectionResponse:
    return get_detection(session, settings, agent_id)


@router.post(
    "/{agent_id}/rf/scans",
    response_model=RfScanResponse,
)
def publish_rf_scan(
    agent_id: str,
    payload: RfScanRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> RfScanResponse:
    token = _bearer_token(authorization)
    agent = authenticate_agent(session, agent_id, token)
    return ingest_rf_scan(session, settings, agent, payload)


@router.get(
    "/{agent_id}/rf/scans/latest",
    response_model=RfLatestScanResponse,
)
def latest_rf_scan(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> RfLatestScanResponse:
    return get_latest_rf_scan(session, agent_id)


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


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent_name(
    agent_id: str,
    payload: RenameAgentRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> AgentResponse:
    return rename_agent(session, settings, agent_id, payload)


@router.get("/{agent_id}/experience/episodes", response_model=ClientEpisodePage)
def client_episodes(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    domain: Annotated[
        str | None, Query(pattern="^(wifi_rf|local_network|dns|internet|application)$")
    ] = None,
):
    from wifi_server.services.client_episodes import list_episodes

    return list_episodes(
        session,
        agent_id,
        settings.agent_offline_after_seconds,
        offset=offset,
        limit=limit,
        domain=domain,
    )


@router.get("/{agent_id}/experience/episodes/{episode_id}", response_model=ClientEpisodeResponse)
def client_episode(
    agent_id: str,
    episode_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
):
    from wifi_server.services.client_episodes import get_episode

    return get_episode(session, agent_id, episode_id, settings.agent_offline_after_seconds)


@router.post("/{agent_id}/experience/episodes/{episode_id}/ack", status_code=204)
def acknowledge_client_episode(
    agent_id: str, episode_id: str, session: Annotated[Session, Depends(get_session)]
) -> None:
    from wifi_server.services.client_episodes import acknowledge_episode

    acknowledge_episode(session, agent_id, episode_id)
