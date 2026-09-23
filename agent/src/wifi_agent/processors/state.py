from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from wifi_agent.core import Observation


@dataclass(frozen=True, slots=True)
class CurrentStateSnapshot:
    observed_at: datetime
    wifi: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    collector_errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "wifi": self.wifi,
            "network": self.network,
            "collector_errors": self.collector_errors,
        }


class StateProcessor:
    """Build a fresh current-state snapshot from one collection cycle."""

    def build(
        self,
        observations: list[Observation],
        collector_errors: list[str] | None = None,
    ) -> CurrentStateSnapshot:
        wifi: dict[str, Any] = {}
        network: dict[str, Any] = {}
        observed_at = max(
            (observation.observed_at for observation in observations),
            default=datetime.now(UTC),
        )

        for observation in observations:
            domain, separator, key = observation.metric.partition(".")
            if not separator or not key:
                continue
            if domain == "wifi":
                wifi[key] = observation.value
            elif domain == "network":
                network[key] = observation.value

        return CurrentStateSnapshot(
            observed_at=observed_at,
            wifi=wifi,
            network=network,
            collector_errors=list(collector_errors or []),
        )
