from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CapabilityPayload(BaseModel):
    capability: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEnrollmentRequest(BaseModel):
    enrollment_token: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=128)
    hostname: str = Field(min_length=1, max_length=255)
    agent_type: str = Field(min_length=1, max_length=32)
    agent_version: str = Field(min_length=1, max_length=64)
    os_name: str | None = Field(default=None, max_length=128)
    os_version: str | None = Field(default=None, max_length=128)
    capabilities: list[CapabilityPayload] = Field(default_factory=list)


class AgentEnrollmentResponse(BaseModel):
    agent_id: str
    agent_token: str
    config_revision: int
    enrolled_at: datetime


class RecordingHeartbeat(BaseModel):
    active: bool
    recording_id: str | None = None


class AgentHeartbeatRequest(BaseModel):
    timestamp: datetime
    agent_version: str = Field(min_length=1, max_length=64)
    config_revision: int = Field(default=0, ge=0)
    recording: RecordingHeartbeat
    health: dict[str, str] = Field(default_factory=dict)


class AgentHeartbeatResponse(BaseModel):
    server_time: datetime
    desired_config_revision: int
    commands: list[dict[str, Any]] = Field(default_factory=list)


class AgentCapabilityResponse(BaseModel):
    capability: str
    enabled: bool
    metadata: dict[str, Any]


class AgentResponse(BaseModel):
    id: str
    name: str
    hostname: str
    agent_type: str
    status: str
    os_name: str | None
    os_version: str | None
    agent_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    capabilities: list[AgentCapabilityResponse] = Field(default_factory=list)
