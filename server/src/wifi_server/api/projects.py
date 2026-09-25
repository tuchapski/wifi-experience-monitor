"""Endpoints for grouped diagnostic projects and their runs."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.dependencies import get_session, get_settings
from wifi_server.project_schemas import CreateProjectRequest, ProjectResponse, ProjectRunResponse
from wifi_server.services.projects import create_project, list_projects, start_project_run

router = APIRouter(prefix="/api/v1/diagnostic-projects", tags=["diagnostic-projects"])


@router.get("", response_model=list[ProjectResponse])
def projects(session: Annotated[Session, Depends(get_session)]) -> list[ProjectResponse]:
    return list_projects(session)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def new_project(
    payload: CreateProjectRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectResponse:
    return create_project(session, payload)


@router.post("/{project_id}/runs", response_model=ProjectRunResponse, status_code=201)
def start_run(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[ServerSettings, Depends(get_settings)],
) -> ProjectRunResponse:
    return start_project_run(session, settings, project_id)
