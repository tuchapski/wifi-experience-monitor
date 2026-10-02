"""Versioned, client-specific runtime policy and explainable detector output."""

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


class ServiceObjectives(BaseModel):
    model_config = {"extra": "forbid"}
    latency_ms: float | None = Field(default=None, gt=0, le=60000, allow_inf_nan=False)
    packet_loss_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    jitter_ms: float | None = Field(default=None, gt=0, le=60000, allow_inf_nan=False)
    ttfb_ms: float | None = Field(default=None, gt=0, le=60000, allow_inf_nan=False)


class ExperienceProfile(BaseModel):
    model_config = {"extra": "forbid"}

    enabled: bool = False
    name: str = Field(default="Office client", min_length=1, max_length=128)
    location: str = Field(default="", max_length=128)
    dns_query: str = Field(default="example.com", min_length=1, max_length=253)
    internet_target: str = Field(default="1.1.1.1", min_length=1, max_length=253)
    https_url: str = Field(default="https://example.com", min_length=1, max_length=2048)
    interval_seconds: float = Field(default=5, ge=5, le=20, allow_inf_nan=False)
    timeout_seconds: float = Field(default=6, ge=1, le=10, allow_inf_nan=False)
    confirm_seconds: float = Field(default=15, ge=5, le=300, allow_inf_nan=False)
    recover_seconds: float = Field(default=10, ge=5, le=300, allow_inf_nan=False)
    minimum_samples: int = Field(default=3, ge=2, le=20)
    baseline_min_samples: int = Field(default=30, ge=10, le=120)
    baseline_min_seconds: float = Field(default=120, ge=30, le=3600, allow_inf_nan=False)
    automatic_capture: bool = False
    capture_pre_seconds: int = Field(default=120, ge=0, le=300)
    capture_post_seconds: int = Field(default=300, ge=30, le=900)
    capture_cooldown_seconds: int = Field(default=300, ge=30, le=3600)
    local_network: ServiceObjectives = Field(
        default_factory=lambda: ServiceObjectives(latency_ms=50, packet_loss_percent=1)
    )
    dns: ServiceObjectives = Field(default_factory=lambda: ServiceObjectives(latency_ms=150))
    internet: ServiceObjectives = Field(
        default_factory=lambda: ServiceObjectives(latency_ms=150, packet_loss_percent=1)
    )
    application: ServiceObjectives = Field(
        default_factory=lambda: ServiceObjectives(latency_ms=2000)
    )

    @field_validator("name", "location")
    @classmethod
    def trim(cls, value: str) -> str:
        if value and not value.strip():
            raise ValueError("Use non-blank text")
        return value.strip()

    @field_validator("dns_query", "internet_target")
    @classmethod
    def target(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-]*", value):
            raise ValueError("Use a hostname or IP address without spaces or command options")
        return value

    @field_validator("https_url")
    @classmethod
    def url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Use an HTTPS URL without credentials or whitespace")
        _ = parsed.port  # Reject invalid ports as well.
        return value

    @model_validator(mode="after")
    def reference_window(self) -> "ExperienceProfile":
        if self.baseline_min_seconds > 119 * self.interval_seconds:
            raise ValueError(
                "Reference duration exceeds the bounded 120-sample window at this cadence"
            )
        return self


class ExperienceProfileResponse(BaseModel):
    agent_id: str
    version: str | None
    applied_version: str | None
    profile: ExperienceProfile


class ExperienceProfileUpdate(BaseModel):
    expected_version: str | None = None
    profile: ExperienceProfile


class BaselineEvidence(BaseModel):
    status: Literal["forming", "ready", "not_applicable"] = "not_applicable"
    samples: int = 0
    median: float | None = None
    mad: float | None = None
    p95: float | None = None
    upper_limit: float | None = None
    established_at: datetime | None = None


class DetectionFinding(BaseModel):
    rule_id: str
    domain: str
    metric: str
    label: str
    status: Literal["unknown", "normal", "candidate", "active", "recovering", "recovered"]
    previous_status: str | None = None
    kind: Literal["availability", "objective", "relative", "none"] = "none"
    reason: str
    target: str | None = None
    value: bool | float | None = None
    unit: str | None = None
    objective: float | None = None
    observed_at: datetime | None = None
    since: datetime | None = None
    observed_duration_seconds: float = 0
    consecutive_samples: int = 0
    evidence_gap: bool = False
    context: dict[str, str] = Field(default_factory=dict)
    baseline: BaselineEvidence = Field(default_factory=BaselineEvidence)


class ClientDetectionResponse(BaseModel):
    agent_id: str
    detector_version: str = "client-detector-v1"
    evaluated_at: datetime
    profile_version: str | None
    applied_version: str | None
    enabled: bool
    status: Literal[
        "disabled", "pending_profile", "unknown", "observed_ok", "candidate", "active", "recovering"
    ]
    active_count: int
    findings: list[DetectionFinding]
    limitations: list[str]
