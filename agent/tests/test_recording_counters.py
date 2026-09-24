from datetime import UTC, datetime, timedelta

from wifi_agent.core import Observation, ObservationKind
from wifi_agent.recording.counters import CounterDeltaProcessor


def _cycle(
    observed_at: datetime,
    bssid: str,
    tx_packets: int,
    tx_retries: int,
    tx_failed: int,
) -> list[Observation]:
    labels = {"interface": "wlp0s20f3"}
    values: list[tuple[str, object, ObservationKind]] = [
        ("wifi.connected", True, ObservationKind.STATE),
        ("wifi.bssid", bssid, ObservationKind.STATE),
        ("wifi.tx_packets", tx_packets, ObservationKind.GAUGE),
        ("wifi.tx_retries", tx_retries, ObservationKind.GAUGE),
        ("wifi.tx_failed", tx_failed, ObservationKind.GAUGE),
    ]
    return [
        Observation(
            source="wifi",
            metric=metric,
            value=value,
            kind=kind,
            observed_at=observed_at,
            labels=labels,
        )
        for metric, value, kind in values
    ]


def _values(observations: list[Observation]) -> dict[str, float]:
    return {
        observation.metric: float(observation.value)
        for observation in observations
        if isinstance(observation.value, (int, float)) and not isinstance(observation.value, bool)
    }


def test_counter_delta_processor_calculates_interval_rates() -> None:
    processor = CounterDeltaProcessor()
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)

    assert processor.consume(_cycle(started, "aa:bb:cc:dd:ee:ff", 100, 10, 1)) == []
    derived = processor.consume(
        _cycle(
            started + timedelta(seconds=1),
            "aa:bb:cc:dd:ee:ff",
            120,
            14,
            2,
        )
    )
    values = _values(derived)

    assert values["wifi.tx_packets_delta"] == 20
    assert values["wifi.tx_retries_delta"] == 4
    assert values["wifi.tx_failed_delta"] == 1
    assert values["wifi.tx_retries_per_100_packets"] == 20
    assert values["wifi.tx_failed_percent"] == 5


def test_counter_delta_processor_resets_on_bssid_change() -> None:
    processor = CounterDeltaProcessor()
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    processor.consume(_cycle(started, "aa:aa:aa:aa:aa:aa", 100, 10, 1))

    changed = processor.consume(
        _cycle(
            started + timedelta(seconds=1),
            "bb:bb:bb:bb:bb:bb",
            5,
            1,
            0,
        )
    )
    comparable = processor.consume(
        _cycle(
            started + timedelta(seconds=2),
            "bb:bb:bb:bb:bb:bb",
            15,
            3,
            0,
        )
    )

    assert changed == []
    assert _values(comparable)["wifi.tx_retries_per_100_packets"] == 20


def test_counter_delta_processor_discards_counter_reset_interval() -> None:
    processor = CounterDeltaProcessor()
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    processor.consume(_cycle(started, "aa:bb:cc:dd:ee:ff", 100, 10, 1))

    reset = processor.consume(
        _cycle(
            started + timedelta(seconds=1),
            "aa:bb:cc:dd:ee:ff",
            3,
            0,
            0,
        )
    )
    comparable = processor.consume(
        _cycle(
            started + timedelta(seconds=2),
            "aa:bb:cc:dd:ee:ff",
            13,
            1,
            0,
        )
    )

    assert reset == []
    assert _values(comparable)["wifi.tx_packets_delta"] == 10
    assert _values(comparable)["wifi.tx_retries_per_100_packets"] == 10
