"""Download standalone reports from persisted recording evidence."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from wifi_server.dependencies import get_session
from wifi_server.services.reports import get_recording_report

router = APIRouter(prefix="/api/v1/recordings", tags=["recording-reports"])


@router.get("/{recording_id}/report/html", response_class=HTMLResponse)
def recording_html_report(
    recording_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", recording_id)[:64]
    return HTMLResponse(
        get_recording_report(session, recording_id),
        headers={"Content-Disposition": f'attachment; filename="recording-{safe_id}.html"'},
    )
