from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RecordingAnalysisResponse(BaseModel):
    id: str
    recording_id: str
    engine_version: str
    status: str
    source_metrics_count: int
    source_events_count: int
    summary: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
