"""Request and response shapes for multi-Agent diagnostic projects."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    objective: str | None = Field(default=None, max_length=2000)
    site: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    profile_id: str = Field(default="wifi-deep-dive", min_length=1, max_length=64)
    max_duration_minutes: int = Field(default=60, ge=1, le=1440)
    agent_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank")
        return value

    @field_validator("objective", "site", "location")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("agent_ids")
    @classmethod
    def validate_agent_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value) or len(value) != len(set(value)):
            raise ValueError("Select unique Agent IDs")
        return value


class ProjectFindingResponse(BaseModel):
    code: str
    severity: str
    title: str


class ProjectAnalysisSummary(BaseModel):
    engine_version: str
    assessment: str
    evidence_status: str
    findings_count: int
    top_findings: list[ProjectFindingResponse]


class ProjectRecordingResponse(BaseModel):
    agent_id: str
    recording_id: str | None
    status: str | None
    sync_status: str | None
    analysis: ProjectAnalysisSummary | None = None


class ProjectRunResponse(BaseModel):
    id: str
    project_id: str
    started_at: datetime
    recordings: list[ProjectRecordingResponse]


class ProjectResponse(BaseModel):
    id: str
    name: str
    objective: str | None
    site: str | None
    location: str | None
    profile_id: str
    max_duration_minutes: int
    agent_ids: list[str]
    created_at: datetime
    runs: list[ProjectRunResponse]
