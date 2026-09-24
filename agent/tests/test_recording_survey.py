from datetime import UTC, datetime, timedelta

from wifi_agent.core import Observation, ObservationKind
from wifi_agent.recording.survey import SurveyDeltaProcessor


def _cycle(
    observed_at: datetime,
    frequency_mhz: int,
    channel_width_mhz: int,
    active_ms: int,
    busy_ms: int,
    rx_ms: int,
    tx_ms: int,
) -> list[Observation]:
    labels = {"interface": "wlp0s20f3"}
    values: list[tuple[str, object, ObservationKind, str | None]] = [
        ("wifi.connected", True, ObservationKind.STATE, None),
        ("wifi.frequency_mhz", frequency_mhz, ObservationKind.STATE, "MHz"),
        ("wifi.channel_width_mhz", channel_width_mhz, ObservationKind.STATE, "MHz"),
        ("wifi.survey_active_ms", active_ms, ObservationKind.GAUGE, "ms"),
        ("wifi.survey_busy_ms", busy_ms, ObservationKind.GAUGE, "ms"),
        ("wifi.survey_rx_ms", rx_ms, ObservationKind.GAUGE, "ms"),
        ("wifi.survey_tx_ms", tx_ms, ObservationKind.GAUGE, "ms"),
    ]
    return [
        Observation(
            source="wifi",
            metric=metric,
            value=value,
            kind=kind,
            unit=unit,
            observed_at=observed_at,
            labels=labels,
        )
        for metric, value, kind, unit in values
    ]


def _values(observations: list[Observation]) -> dict[str, float]:
    return {
        observation.metric: float(observation.value)
        for observation in observations
        if isinstance(observation.value, (int, float)) and not isinstance(observation.value, bool)
    }


def test_survey_delta_processor_calculates_interval_utilization() -> None:
    processor = SurveyDeltaProcessor()
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)

    assert processor.consume(_cycle(started, 5220, 80, 1000, 400, 200, 100)) == []
    derived = processor.consume(
        _cycle(
            started + timedelta(seconds=1),
            5220,
            80,
            1100,
            470,
            240,
            120,
        )
    )
    values = _values(derived)

    assert values["wifi.survey_active_ms_delta"] == 100
    assert values["wifi.channel_utilization_percent"] == 70
    assert values["wifi.channel_rx_percent"] == 40
    assert values["wifi.channel_tx_percent"] == 20


def test_survey_delta_processor_resets_on_channel_change() -> None:
    processor = SurveyDeltaProcessor()
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    processor.consume(_cycle(started, 5180, 80, 1000, 500, 300, 100))

    changed = processor.consume(
        _cycle(
            started + timedelta(seconds=1),
            5220,
            80,
            50,
            10,
            5,
            2,
        )
    )
    comparable = processor.consume(
        _cycle(
            started + timedelta(seconds=2),
            5220,
            80,
            150,
            60,
            25,
            12,
        )
    )

    assert changed == []
    assert _values(comparable)["wifi.channel_utilization_percent"] == 50


def test_survey_delta_processor_discards_counter_reset_interval() -> None:
    processor = SurveyDeltaProcessor()
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    processor.consume(_cycle(started, 5220, 80, 1000, 400, 200, 100))

    reset = processor.consume(
        _cycle(
            started + timedelta(seconds=1),
            5220,
            80,
            100,
            20,
            10,
            5,
        )
    )
    comparable = processor.consume(
        _cycle(
            started + timedelta(seconds=2),
            5220,
            80,
            200,
            50,
            30,
            15,
        )
    )

    assert reset == []
    assert _values(comparable)["wifi.channel_utilization_percent"] == 30
