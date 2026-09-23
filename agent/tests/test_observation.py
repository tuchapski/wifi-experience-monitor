from datetime import UTC, datetime

import pytest
from wifi_agent.core.observation import Observation, ObservationKind


def test_observation_defaults_to_timezone_aware_timestamp() -> None:
    observation = Observation(
        source="wifi.station",
        kind=ObservationKind.GAUGE,
        metric="wifi.rssi",
        value=-53,
        unit="dBm",
    )

    assert observation.observed_at.tzinfo is not None


def test_observation_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Observation(
            source="wifi.station",
            kind=ObservationKind.GAUGE,
            metric="wifi.rssi",
            value=-53,
            observed_at=datetime(2026, 9, 23, 12, 0, 0),
        )


def test_observation_accepts_explicit_utc_timestamp() -> None:
    observed_at = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)

    observation = Observation(
        source="network.gateway",
        kind=ObservationKind.RESULT,
        metric="network.gateway.latency",
        value=2.8,
        unit="ms",
        observed_at=observed_at,
    )

    assert observation.observed_at == observed_at
