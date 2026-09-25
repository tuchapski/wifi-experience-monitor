import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.recording_models import AgentCommand
from wifi_server.dependencies import get_database, get_session
from wifi_server.recording_schemas import (
    AgentCommandAckRequest,
    RecordingBatchRequest,
    RecordingBatchResponse,
    RecordingEventResponse,
    RecordingManifestRequest,
    RecordingManifestResponse,
    RecordingMetricOverview,
    RecordingMetricResponse,
    RecordingResponse,
    StartRecordingRequest,
)
from wifi_server.services.agents import authenticate_agent
from wifi_server.services.analyses import ensure_recording_analysis
from wifi_server.services.metric_overviews import get_metric_overviews
from wifi_server.services.recordings import (
    acknowledge_command,
    create_recording,
    finalize_manifest,
    get_recording,
    get_recording_events,
    get_recording_metrics,
    ingest_recording_batch,
    list_recordings,
    request_stop_recording,
)

router = APIRouter(prefix="/api/v1", tags=["recordings"])
logger = logging.getLogger(__name__)


def _analyze_completed_recording(recording_id: str) -> None:
    try:
        with get_database().session() as session:
            ensure_recording_analysis(session, recording_id)
    except Exception:
        logger.exception("Automatic analysis failed for recording %s", recording_id)


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


@router.post(
    "/agents/{agent_id}/recordings",
    response_model=RecordingResponse,
    status_code=201,
)
def start_recording(
    agent_id: str,
    payload: StartRecordingRequest,
    session: Annotated[Session, Depends(get_session)],
) -> RecordingResponse:
    return create_recording(session, agent_id, payload)


@router.get(
    "/agents/{agent_id}/recordings",
    response_model=list[RecordingResponse],
)
def recordings(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> list[RecordingResponse]:
    return list_recordings(session, agent_id)


@router.get("/recordings/{recording_id}", response_model=RecordingResponse)
def recording(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> RecordingResponse:
    return get_recording(session, recording_id)


@router.get(
    "/recordings/{recording_id}/metrics/overview",
    response_model=list[RecordingMetricOverview],
)
def recording_metric_overviews(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
    metric: Annotated[list[str], Query()],
    buckets: Annotated[int, Query(ge=20, le=500)] = 300,
) -> list[RecordingMetricOverview]:
    if not metric or len(metric) > 20 or any(not item or len(item) > 128 for item in metric):
        raise HTTPException(status_code=422, detail="Select between 1 and 20 metric names")
    return get_metric_overviews(session, recording_id, list(dict.fromkeys(metric)), buckets)


@router.get(
    "/recordings/{recording_id}/metrics",
    response_model=list[RecordingMetricResponse],
)
def recording_metrics(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
    metric: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=50000)] = 20000,
) -> list[RecordingMetricResponse]:
    return get_recording_metrics(session, recording_id, metric, limit)


@router.get(
    "/recordings/{recording_id}/events",
    response_model=list[RecordingEventResponse],
)
def recording_events(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
) -> list[RecordingEventResponse]:
    return get_recording_events(session, recording_id, limit)


@router.post("/recordings/{recording_id}/stop", response_model=RecordingResponse)
def stop_recording(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> RecordingResponse:
    return request_stop_recording(session, recording_id)


@router.post("/commands/{command_id}/ack", status_code=204)
def command_ack(
    command_id: str,
    payload: AgentCommandAckRequest,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    command = session.get(AgentCommand, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")
    token = _bearer_token(authorization)
    authenticate_agent(session, command.agent_id, token)
    acknowledge_command(session, command, payload)


@router.post(
    "/recordings/{recording_id}/batches",
    response_model=RecordingBatchResponse,
)
def recording_batch(
    recording_id: str,
    payload: RecordingBatchRequest,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> RecordingBatchResponse:
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    token = _bearer_token(authorization)
    authenticate_agent(session, recording.agent_id, token)
    return ingest_recording_batch(session, recording, payload)


@router.post(
    "/recordings/{recording_id}/manifest",
    response_model=RecordingManifestResponse,
)
def recording_manifest(
    recording_id: str,
    payload: RecordingManifestRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> RecordingManifestResponse:
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    token = _bearer_token(authorization)
    authenticate_agent(session, recording.agent_id, token)
    result = finalize_manifest(session, recording, payload)
    if result.sync_status == "complete":
        background_tasks.add_task(_analyze_completed_recording, recording_id)
    return result
