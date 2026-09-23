from datetime import UTC, datetime, timedelta

from wifi_agent.core import Observation, ObservationKind
from wifi_agent.processors import TelemetryAggregator, TelemetryPoint
from wifi_agent.storage import TelemetrySpool


def _observation(
    metric: str,
    value: int | float,
    observed_at: datetime,
    kind: ObservationKind = ObservationKind.GAUGE,
) -> Observation:
    return Observation(
        source="wifi",
        kind=kind,
        metric=metric,
        value=value,
        unit="dBm" if "dbm" in metric else None,
        observed_at=observed_at,
        labels={"interface": "wlp0s20f3"},
    )


def test_telemetry_aggregator_builds_window_statistics() -> None:
    started = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
    aggregator = TelemetryAggregator(window_seconds=10)

    aggregator.consume(
        [
            _observation("wifi.rssi_dbm", -50, started),
            _observation("wifi.tx_packets", 100, started),
        ]
    )
    aggregator.consume([_observation("wifi.rssi_dbm", -60, started + timedelta(seconds=10))])

    points = aggregator.flush_if_due(started + timedelta(seconds=10))

    assert len(points) == 1
    assert points[0].metric == "wifi.rssi_dbm"
    assert points[0].value == -55
    assert points[0].min_value == -60
    assert points[0].max_value == -50
    assert points[0].sample_count == 2


def test_telemetry_aggregator_ignores_state_observations() -> None:
    observed_at = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
    aggregator = TelemetryAggregator(window_seconds=10)
    aggregator.consume(
        [
            _observation(
                "wifi.rssi_dbm",
                -50,
                observed_at,
                kind=ObservationKind.STATE,
            )
        ]
    )

    assert aggregator.flush() == []


def test_telemetry_spool_persists_sequence_and_acknowledgement(tmp_path) -> None:
    spool = TelemetrySpool(tmp_path / "agent.db")
    spool.initialize()
    observed_at = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
    point = TelemetryPoint(
        observed_at=observed_at,
        metric="wifi.rssi_dbm",
        value=-52,
        min_value=-54,
        max_value=-50,
        sample_count=10,
        unit="dBm",
        labels={"interface": "wlp0s20f3"},
    )

    first = spool.enqueue([point], observed_at)
    second = spool.enqueue([point], observed_at + timedelta(seconds=10))

    assert first is not None
    assert second is not None
    assert first.sequence == 1
    assert second.sequence == 2
    assert spool.pending_count() == 2
    assert [batch.sequence for batch in spool.pending()] == [1, 2]

    spool.acknowledge(first.batch_id)

    assert spool.pending_count() == 1
    assert spool.pending()[0].batch_id == second.batch_id
