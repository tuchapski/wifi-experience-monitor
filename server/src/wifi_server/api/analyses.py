from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from wifi_server.analysis_schemas import RecordingAnalysisResponse
from wifi_server.dependencies import get_session
from wifi_server.services.analyses import (
    get_latest_recording_analysis,
    run_recording_analysis,
)

router = APIRouter(prefix="/api/v1/recordings", tags=["recording-analysis"])


@router.post(
    "/{recording_id}/analysis",
    response_model=RecordingAnalysisResponse,
    status_code=201,
)
def analyze(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> RecordingAnalysisResponse:
    return run_recording_analysis(session, recording_id)


@router.get(
    "/{recording_id}/analysis/latest",
    response_model=RecordingAnalysisResponse,
)
def latest_analysis(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> RecordingAnalysisResponse:
    return get_latest_recording_analysis(session, recording_id)
