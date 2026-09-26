from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from wifi_server.db.models import DiagnosticRecording
from wifi_server.db.project_models import ProjectRunRecording
from wifi_server.services.recording_deletion import delete_recording_dataset


def _recording(recording_status: str = "completed") -> DiagnosticRecording:
    return DiagnosticRecording(id="rec_delete", status=recording_status)


def test_delete_completed_individual_recording() -> None:
    recording = _recording()
    session = Mock(spec=Session)
    session.get.return_value = recording
    session.scalar.return_value = None

    delete_recording_dataset(session, recording.id)

    session.delete.assert_called_once_with(recording)
    session.commit.assert_called_once()


@pytest.mark.parametrize("recording_status", ["created", "recording", "stopping"])
def test_delete_rejects_active_recording(recording_status: str) -> None:
    recording = _recording(recording_status)
    session = Mock(spec=Session)
    session.get.return_value = recording

    with pytest.raises(HTTPException) as exc_info:
        delete_recording_dataset(session, recording.id)

    assert exc_info.value.status_code == 409
    session.delete.assert_not_called()
    session.commit.assert_not_called()


def test_delete_rejects_project_recording() -> None:
    recording = _recording()
    session = Mock(spec=Session)
    session.get.return_value = recording
    session.scalar.return_value = Mock(spec=ProjectRunRecording)

    with pytest.raises(HTTPException) as exc_info:
        delete_recording_dataset(session, recording.id)

    assert exc_info.value.status_code == 409
    session.delete.assert_not_called()
    session.commit.assert_not_called()
