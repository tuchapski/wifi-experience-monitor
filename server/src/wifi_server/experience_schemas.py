"""Current client observations and their evidence quality, without causal inference."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ExperienceStatus = Literal[
    "observed_ok", "degraded", "failure", "partial", "unavailable", "stale", "collection_error"
]
MeasurementQuality = Literal["current", "legacy", "stale", "unavailable", "invalid"]


class ExperienceMeasurement(BaseModel):
    metric: str
    label: str
    value: bool | float | str | None
    unit: str | None
    quality: MeasurementQuality
    observed_at: datetime | None
    source: str | None
    age_seconds: float | None
    sample_count: int | None
    interval_seconds: float | None
    target: str | None
    profile_version: str | None


class ExperienceDomain(BaseModel):
    domain: str
    label: str
    status: ExperienceStatus
    explanation: str
    target: str | None
    measurements: list[ExperienceMeasurement]


class ClientExperienceResponse(BaseModel):
    agent_id: str
    version: str = "client-experience-v1"
    evaluated_at: datetime
    state_observed_at: datetime | None
    state_received_at: datetime | None
    agent_online: bool
    max_measurement_age_seconds: float = 30
    status: ExperienceStatus
    current_outcomes: int
    total_outcomes: int = 5
    outcome_coverage_percent: float
    domains: list[ExperienceDomain]
    collector_errors: list[str]
    limitations: list[str]
