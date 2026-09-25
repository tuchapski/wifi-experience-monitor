from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StartRecordingRequest(BaseModel):
    name: str = Field(default="Diagnostic Recording", min_length=1, max_length=255)
    description: str | None = None
    profile_id: str = Field(default="wifi-deep-dive", min_length=1, max_length=64)
    max_duration_minutes: int = Field(default=60, ge=1, le=1440)


class RecordingResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    description: str | None
    status: str
    sync_status: str
    profile_id: str | None
    max_duration_minutes: int | None
    started_at: datetime | None
    ended_at: datetime | None
    agent_version: str | None
    schema_version: int
    metrics_count: int
    events_count: int
    tests_count: int
    artifacts_count: int
    created_at: datetime
    updated_at: datetime


class RecordingMetricResponse(BaseModel):
    observed_at: datetime
    metric: str
    value: float
    unit: str | None
    labels: dict[str, Any]
    received_at: datetime


class RecordingEventResponse(BaseModel):
    observed_at: datetime
    event_type: str
    severity: str
    data: dict[str, Any]
    received_at: datetime


class AgentCommandAckRequest(BaseModel):
    status: Literal["acked", "failed"]
    data: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class RecordingMetricPayload(BaseModel):
    observed_at: datetime
    metric: str = Field(min_length=1, max_length=128)
    value: float
    unit: str | None = Field(default=None, max_length=32)
    labels: dict[str, Any] = Field(default_factory=dict)


class RecordingEventPayload(BaseModel):
    observed_at: datetime
    event_type: str = Field(min_length=1, max_length=128)
    severity: str = Field(default="info", min_length=1, max_length=32)
    data: dict[str, Any] = Field(default_factory=dict)


class RecordingBatchRequest(BaseModel):
    batch_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=1)
    metrics: list[RecordingMetricPayload] = Field(default_factory=list)
    events: list[RecordingEventPayload] = Field(default_factory=list)


class RecordingBatchResponse(BaseModel):
    batch_id: str
    sequence: int
    status: str
    metrics_received: int
    events_received: int


class RecordingManifestRequest(BaseModel):
    ended_at: datetime
    batches_count: int = Field(ge=0)
    metrics_count: int = Field(ge=0)
    events_count: int = Field(ge=0)
    tests_count: int = Field(default=0, ge=0)
    artifacts_count: int = Field(default=0, ge=0)


class RecordingManifestResponse(BaseModel):
    recording_id: str
    status: str
    sync_status: str
    missing_sequences: list[int] = Field(default_factory=list)
