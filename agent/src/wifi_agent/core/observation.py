from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeAlias


class ObservationKind(StrEnum):
    """Semantic category of an observation produced by an agent collector."""

    GAUGE = "gauge"
    STATE = "state"
    EVENT = "event"
    RESULT = "result"


ObservationValue: TypeAlias = int | float | str | bool | None


@dataclass(frozen=True, slots=True)
class Observation:
    """Collector output contract consumed by state, telemetry and recording processors."""

    source: str
    kind: ObservationKind
    metric: str
    value: ObservationValue = None
    unit: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    labels: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("observation source must not be empty")
        if not self.metric.strip():
            raise ValueError("observation metric must not be empty")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
