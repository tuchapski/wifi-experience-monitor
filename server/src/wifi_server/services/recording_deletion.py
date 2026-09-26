"""Delete completed individual diagnostic recordings and their dependent evidence."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.project_models import ProjectRunRecording

ACTIVE_RECORDING_STATUSES = {"created", "recording", "stopping"}


def delete_recording_dataset(session: Session, recording_id: str) -> None:
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found",
        )

    if recording.status in ACTIVE_RECORDING_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active recordings cannot be deleted",
        )

    project_recording = session.scalar(
        select(ProjectRunRecording).where(ProjectRunRecording.recording_id == recording_id)
    )
    if project_recording is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project recordings cannot be deleted individually",
        )

    session.delete(recording)
    session.commit()
