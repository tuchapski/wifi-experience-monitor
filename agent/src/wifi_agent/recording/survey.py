from dataclasses import dataclass
from datetime import datetime

from wifi_agent.core import Observation, ObservationKind

SURVEY_COUNTERS = (
    "wifi.survey_active_ms",
    "wifi.survey_busy_ms",
    "wifi.survey_rx_ms",
    "wifi.survey_tx_ms",
)


@dataclass(frozen=True, slots=True)
class SurveySnapshot:
    observed_at: datetime
    frequency_mhz: int
    channel_width_mhz: int
    labels: dict[str, str]
    values: dict[str, int]


class SurveyDeltaProcessor:
    """Convert cumulative survey counters into same-channel interval percentages."""

    def __init__(self) -> None:
        self._previous: SurveySnapshot | None = None

    def reset(self) -> None:
        self._previous = None

    def consume(self, observations: list[Observation]) -> list[Observation]:
        current = self._snapshot(observations)
        if current is None:
            self.reset()
            return []

        previous = self._previous
        self._previous = current
        if previous is None:
            return []
        if (
            previous.frequency_mhz != current.frequency_mhz
            or previous.channel_width_mhz != current.channel_width_mhz
        ):
            return []

        interval_seconds = (current.observed_at - previous.observed_at).total_seconds()
        if interval_seconds <= 0:
            return []

        deltas: dict[str, int] = {}
        for metric in SURVEY_COUNTERS:
            before = previous.values.get(metric)
            after = current.values.get(metric)
            if before is None or after is None:
                continue
            if after < before:
                return []
            deltas[metric] = after - before

        active_delta = deltas.get("wifi.survey_active_ms")
        if active_delta is None or active_delta <= 0:
            return []

        labels = {
            **current.labels,
            "frequency_mhz": str(current.frequency_mhz),
            "channel_width_mhz": str(current.channel_width_mhz),
            "interval_seconds": f"{interval_seconds:.3f}",
        }
        derived = [
            self._observation(
                current,
                "wifi.survey_active_ms_delta",
                float(active_delta),
                "ms",
                labels,
            )
        ]
        for source_metric, derived_metric in (
            ("wifi.survey_busy_ms", "wifi.channel_utilization_percent"),
            ("wifi.survey_rx_ms", "wifi.channel_rx_percent"),
            ("wifi.survey_tx_ms", "wifi.channel_tx_percent"),
        ):
            delta = deltas.get(source_metric)
            if delta is None or delta > active_delta:
                continue
            derived.append(
                self._observation(
                    current,
                    derived_metric,
                    round(100 * delta / active_delta, 3),
                    "%",
                    labels,
                )
            )
        return derived

    @staticmethod
    def _snapshot(observations: list[Observation]) -> SurveySnapshot | None:
        connected: bool | None = None
        frequency_mhz: int | None = None
        channel_width_mhz: int | None = None
        values: dict[str, int] = {}
        labels: dict[str, str] = {}
        observed_at: datetime | None = None

        for observation in observations:
            observed_at = (
                observation.observed_at
                if observed_at is None
                else max(observed_at, observation.observed_at)
            )
            if observation.metric == "wifi.connected":
                connected = observation.value if isinstance(observation.value, bool) else None
            elif observation.metric == "wifi.frequency_mhz":
                value = observation.value
                if isinstance(value, int) and not isinstance(value, bool):
                    frequency_mhz = value
                    labels = dict(observation.labels)
            elif observation.metric == "wifi.channel_width_mhz":
                value = observation.value
                if isinstance(value, int) and not isinstance(value, bool):
                    channel_width_mhz = value
                    if not labels:
                        labels = dict(observation.labels)
            elif observation.metric in SURVEY_COUNTERS:
                value = observation.value
                if isinstance(value, int) and not isinstance(value, bool):
                    values[observation.metric] = value
                    if not labels:
                        labels = dict(observation.labels)

        if (
            connected is not True
            or frequency_mhz is None
            or channel_width_mhz is None
            or observed_at is None
            or "wifi.survey_active_ms" not in values
        ):
            return None
        return SurveySnapshot(
            observed_at=observed_at,
            frequency_mhz=frequency_mhz,
            channel_width_mhz=channel_width_mhz,
            labels=labels,
            values=values,
        )

    @staticmethod
    def _observation(
        snapshot: SurveySnapshot,
        metric: str,
        value: float,
        unit: str,
        labels: dict[str, str],
    ) -> Observation:
        return Observation(
            source="wifi-survey-delta",
            kind=ObservationKind.GAUGE,
            metric=metric,
            value=value,
            unit=unit,
            observed_at=snapshot.observed_at,
            labels=labels,
        )
