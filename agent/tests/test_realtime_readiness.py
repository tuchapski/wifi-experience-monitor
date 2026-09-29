from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from wifi_agent.cli import _fresh_probe_observations, _update_probe_cache
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.processors import TelemetryAggregator
from wifi_agent.runtime.current_state import CurrentStateRuntime


def _survey_cycle(
    observed_at: datetime,
    *,
    active_ms: int | None,
    busy_ms: int | None,
) -> list[Observation]:
    values: list[tuple[str, object, ObservationKind, str | None]] = [
        ("wifi.connected", True, ObservationKind.STATE, None),
        ("wifi.frequency_mhz", 5220, ObservationKind.STATE, "MHz"),
        ("wifi.channel_width_mhz", 80, ObservationKind.STATE, "MHz"),
    ]
    if active_ms is not None:
        values.append(("wifi.survey_active_ms", active_ms, ObservationKind.GAUGE, "ms"))
    if busy_ms is not None:
        values.append(("wifi.survey_busy_ms", busy_ms, ObservationKind.GAUGE, "ms"))
    return [
        Observation(
            source="wifi",
            kind=kind,
            metric=metric,
            value=value,
            unit=unit,
            observed_at=observed_at,
        )
        for metric, value, kind, unit in values
    ]


def test_current_state_marks_rf_survey_verified_and_derives_utilization() -> None:
    runtime = CurrentStateRuntime("wlp0s20f3")
    started = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)

    with (
        patch.object(
            runtime.wifi,
            "collect",
            side_effect=[
                _survey_cycle(started, active_ms=1000, busy_ms=400),
                _survey_cycle(
                    started + timedelta(seconds=1),
                    active_ms=1100,
                    busy_ms=470,
                ),
            ],
        ),
        patch.object(runtime.network, "collect", return_value=[]),
    ):
        first = runtime.collect_cycle()
        second = runtime.collect_cycle()

    assert first.snapshot.wifi["survey_status"] == "verified"
    assert "channel_utilization_percent" not in first.snapshot.wifi
    assert second.snapshot.wifi["survey_status"] == "verified"
    assert second.snapshot.wifi["channel_utilization_percent"] == 70
    assert any(
        item.metric == "wifi.channel_utilization_percent" for item in second.derived_observations
    )


def test_current_state_explains_missing_busy_counter() -> None:
    runtime = CurrentStateRuntime("wlp0s20f3")
    observed_at = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)

    with (
        patch.object(
            runtime.wifi,
            "collect",
            return_value=_survey_cycle(
                observed_at,
                active_ms=1000,
                busy_ms=None,
            ),
        ),
        patch.object(runtime.network, "collect", return_value=[]),
    ):
        cycle = runtime.collect_cycle()

    assert cycle.snapshot.wifi["survey_status"] == "degraded"
    assert "not channel busy time" in cycle.snapshot.wifi["survey_reason"].lower()


def test_current_state_includes_cached_synthetic_observations() -> None:
    runtime = CurrentStateRuntime("wlp0s20f3")
    observed_at = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    synthetic = [
        Observation(
            source="synthetic",
            kind=ObservationKind.GAUGE,
            metric="network.gateway_latency_ms",
            value=4.2,
            unit="ms",
            observed_at=observed_at,
        ),
        Observation(
            source="synthetic",
            kind=ObservationKind.STATE,
            metric="network.dns_success",
            value=True,
            observed_at=observed_at,
        ),
        Observation(
            source="synthetic",
            kind=ObservationKind.GAUGE,
            metric="network.https_total_ms",
            value=210.0,
            unit="ms",
            observed_at=observed_at,
        ),
    ]

    with (
        patch.object(runtime.wifi, "collect", return_value=[]),
        patch.object(runtime.network, "collect", return_value=[]),
    ):
        cycle = runtime.collect_cycle(extra_observations=synthetic)

    assert cycle.snapshot.network["gateway_latency_ms"] == 4.2
    assert cycle.snapshot.network["dns_success"] is True
    assert cycle.snapshot.network["https_total_ms"] == 210.0


def test_channel_utilization_is_part_of_realtime_telemetry() -> None:
    aggregator = TelemetryAggregator(10.0)

    assert "wifi.channel_utilization_percent" in aggregator.metrics
    assert "wifi.channel_rx_percent" in aggregator.metrics
    assert "wifi.channel_tx_percent" in aggregator.metrics


def test_probe_cache_replaces_previous_result_and_expires() -> None:
    observed_at = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    cache: dict[str, Observation] = {}

    _update_probe_cache(
        cache,
        [
            Observation(
                source="synthetic",
                kind=ObservationKind.STATE,
                metric="network.internet_reachable",
                value=True,
                observed_at=observed_at,
            ),
            Observation(
                source="synthetic",
                kind=ObservationKind.GAUGE,
                metric="network.internet_latency_ms",
                value=22.0,
                unit="ms",
                observed_at=observed_at,
            ),
        ],
    )

    _update_probe_cache(
        cache,
        [
            Observation(
                source="synthetic",
                kind=ObservationKind.STATE,
                metric="network.internet_reachable",
                value=False,
                observed_at=observed_at + timedelta(seconds=5),
            ),
            Observation(
                source="synthetic",
                kind=ObservationKind.GAUGE,
                metric="network.internet_packet_loss_percent",
                value=100.0,
                unit="%",
                observed_at=observed_at + timedelta(seconds=5),
            ),
        ],
    )

    assert "network.internet_latency_ms" not in cache

    fresh = _fresh_probe_observations(
        cache,
        15,
        now=observed_at + timedelta(seconds=10),
    )
    assert {item.metric for item in fresh} == {
        "network.internet_reachable",
        "network.internet_packet_loss_percent",
    }

    assert (
        _fresh_probe_observations(
            cache,
            15,
            now=observed_at + timedelta(seconds=30),
        )
        == []
    )
