from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from wifi_agent.core import Observation


@dataclass(frozen=True, slots=True)
class CurrentStateSnapshot:
    observed_at: datetime
    wifi: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    collector_errors: list[str] = field(default_factory=list)
    measurement_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "wifi": self.wifi,
            "network": self.network,
            "collector_errors": self.collector_errors,
            "measurement_metadata": self.measurement_metadata,
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
        metadata: dict[str, dict[str, Any]] = {}
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
            else:
                continue
            interval = observation.labels.get("interval_seconds")
            try:
                interval_seconds = float(interval) if interval is not None else None
            except (ValueError, TypeError):
                interval_seconds = None
            if interval_seconds is not None and (
                not isfinite(interval_seconds) or interval_seconds < 0
            ):
                interval_seconds = None
            metadata[observation.metric] = {
                "observed_at": observation.observed_at.isoformat(),
                "source": observation.source,
                "sample_count": 1,
                "unit": observation.unit,
                "interval_seconds": interval_seconds,
                "labels": dict(observation.labels),
                "profile_version": observation.metadata.get("profile_version"),
            }

        return CurrentStateSnapshot(
            observed_at=observed_at,
            wifi=wifi,
            network=network,
            collector_errors=list(collector_errors or []),
            measurement_metadata=metadata,
        )
