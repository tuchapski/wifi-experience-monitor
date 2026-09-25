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


class WifiCurrentStatePayload(BaseModel):
    model_config = {"extra": "allow"}

    connected: bool | None = None
    interface: str | None = None
    ssid: str | None = None
    bssid: str | None = None
    frequency_mhz: int | None = None
    channel: int | None = None
    channel_width_mhz: int | None = None
    rssi_dbm: float | None = None
    snr_db: float | None = None
    tx_rate_mbps: float | None = None
    rx_rate_mbps: float | None = None
    link_score: dict[str, Any] | None = None


class NetworkCurrentStatePayload(BaseModel):
    model_config = {"extra": "allow"}

    ipv4_address: str | None = None
    prefix_length: int | None = None
    gateway: str | None = None
    gateway_latency_ms: float | None = None
    dns_latency_ms: float | None = None
    internet_latency_ms: float | None = None


class AgentCurrentStateRequest(BaseModel):
    observed_at: datetime
    wifi: WifiCurrentStatePayload = Field(default_factory=WifiCurrentStatePayload)
    network: NetworkCurrentStatePayload = Field(default_factory=NetworkCurrentStatePayload)
    collector_errors: list[str] = Field(default_factory=list)


class AgentCurrentStateResponse(AgentCurrentStateRequest):
    agent_id: str
    updated_at: datetime


class TelemetryItemPayload(BaseModel):
    observed_at: datetime
    metric: str = Field(min_length=1, max_length=128)
    value: float
    min_value: float | None = None
    max_value: float | None = None
    sample_count: int = Field(default=1, ge=1)
    unit: str | None = Field(default=None, max_length=32)
    labels: dict[str, Any] = Field(default_factory=dict)


class TelemetryBatchRequest(BaseModel):
    batch_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=1)
    items: list[TelemetryItemPayload] = Field(min_length=1)


class TelemetryBatchResponse(BaseModel):
    batch_id: str
    sequence: int
    status: str
    items_received: int


class TelemetryPointResponse(BaseModel):
    observed_at: datetime
    metric: str
    value: float
    min_value: float | None
    max_value: float | None
    sample_count: int
    unit: str | None
    labels: dict[str, Any]
    received_at: datetime
