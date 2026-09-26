"""HTTP endpoint for permanent deletion of individual diagnostic recordings."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from wifi_server.dependencies import get_session
from wifi_server.services.recording_deletion import delete_recording_dataset

router = APIRouter(prefix="/api/v1", tags=["recordings"])


@router.delete(
    "/recordings/{recording_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_recording(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    delete_recording_dataset(session, recording_id)
