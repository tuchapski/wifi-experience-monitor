from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from wifi_server.monitor_schemas import DetectionFinding


class EpisodeTransition(BaseModel):
    kind: str
    observed_at: datetime
    data: dict[str, Any]


class EpisodeCaptureResponse(BaseModel):
    recording_id: str | None
    mode: str
    status: str
    requested_start: datetime
    requested_end: datetime
    coverage: dict[str, Any]


class ClientEpisodeResponse(BaseModel):
    id: str
    agent_id: str
    domain: str
    target: str | None
    profile_version: str
    detector_version: str
    status: Literal["active", "recovering", "unknown", "recovered", "interrupted"]
    stored_status: str
    started_at: datetime
    confirmed_at: datetime
    last_observed_at: datetime
    recovered_at: datetime | None
    closed_at: datetime | None
    acknowledged_at: datetime | None
    recurrence_count: int
    observed_duration_seconds: float
    evidence_gap: bool
    reason: str
    context: dict[str, str]
    opening_findings: list[DetectionFinding] = Field(default_factory=list)
    findings: list[DetectionFinding]
    capture: EpisodeCaptureResponse | None = None
    transitions: list[EpisodeTransition] = Field(default_factory=list)
    transitions_truncated: bool = False


class ClientEpisodePage(BaseModel):
    agent_id: str
    evaluated_at: datetime
    total: int
    offset: int
    limit: int
    episodes: list[ClientEpisodeResponse]
