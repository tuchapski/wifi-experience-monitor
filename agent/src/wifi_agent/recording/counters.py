from dataclasses import dataclass
from datetime import datetime

from wifi_agent.core import Observation, ObservationKind

COUNTER_METRICS = (
    "wifi.tx_packets",
    "wifi.tx_retries",
    "wifi.tx_failed",
    "wifi.rx_packets",
    "wifi.rx_drop_misc",
)


@dataclass(frozen=True, slots=True)
class CounterSnapshot:
    observed_at: datetime
    bssid: str
    labels: dict[str, str]
    values: dict[str, int]


class CounterDeltaProcessor:
    """Convert association-scoped cumulative counters into comparable interval metrics."""

    def __init__(self) -> None:
        self._previous: CounterSnapshot | None = None

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
        if previous.bssid != current.bssid:
            return []

        interval_seconds = (current.observed_at - previous.observed_at).total_seconds()
        if interval_seconds <= 0:
            return []

        deltas: dict[str, int] = {}
        for metric in COUNTER_METRICS:
            before = previous.values.get(metric)
            after = current.values.get(metric)
            if before is None or after is None:
                continue
            if after < before:
                return []
            deltas[metric] = after - before

        labels = {
            **current.labels,
            "bssid": current.bssid,
            "interval_seconds": f"{interval_seconds:.3f}",
        }
        derived: list[Observation] = []
        for source_metric, derived_metric, unit in (
            ("wifi.tx_packets", "wifi.tx_packets_delta", "packets"),
            ("wifi.tx_retries", "wifi.tx_retries_delta", "retries"),
            ("wifi.tx_failed", "wifi.tx_failed_delta", "failures"),
            ("wifi.rx_packets", "wifi.rx_packets_delta", "packets"),
            ("wifi.rx_drop_misc", "wifi.rx_drop_misc_delta", "drops"),
        ):
            value = deltas.get(source_metric)
            if value is not None:
                derived.append(
                    self._observation(
                        current,
                        derived_metric,
                        float(value),
                        unit,
                        labels,
                    )
                )

        tx_packets = deltas.get("wifi.tx_packets")
        tx_retries = deltas.get("wifi.tx_retries")
        tx_failed = deltas.get("wifi.tx_failed")
        rx_packets = deltas.get("wifi.rx_packets")
        rx_drop_misc = deltas.get("wifi.rx_drop_misc")

        if tx_packets is not None and tx_packets > 0:
            if tx_retries is not None:
                derived.append(
                    self._observation(
                        current,
                        "wifi.tx_retries_per_100_packets",
                        round(100 * tx_retries / tx_packets, 3),
                        "/100 packets",
                        labels,
                    )
                )
            if tx_failed is not None:
                derived.append(
                    self._observation(
                        current,
                        "wifi.tx_failed_percent",
                        round(100 * tx_failed / tx_packets, 3),
                        "%",
                        labels,
                    )
                )

        if rx_packets is not None and rx_packets > 0 and rx_drop_misc is not None:
            derived.append(
                self._observation(
                    current,
                    "wifi.rx_drop_percent",
                    round(100 * rx_drop_misc / rx_packets, 3),
                    "%",
                    labels,
                )
            )

        return derived

    @staticmethod
    def _snapshot(observations: list[Observation]) -> CounterSnapshot | None:
        connected: bool | None = None
        bssid: str | None = None
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
            elif observation.metric == "wifi.bssid" and isinstance(
                observation.value,
                str,
            ):
                bssid = observation.value
                labels = dict(observation.labels)
            elif observation.metric in COUNTER_METRICS:
                value = observation.value
                if isinstance(value, int) and not isinstance(value, bool):
                    values[observation.metric] = value
                    if not labels:
                        labels = dict(observation.labels)

        if connected is not True or not bssid or observed_at is None:
            return None
        if not values:
            return None
        return CounterSnapshot(
            observed_at=observed_at,
            bssid=bssid,
            labels=labels,
            values=values,
        )

    @staticmethod
    def _observation(
        snapshot: CounterSnapshot,
        metric: str,
        value: float,
        unit: str,
        labels: dict[str, str],
    ) -> Observation:
        return Observation(
            source="wifi-counter-delta",
            kind=ObservationKind.GAUGE,
            metric=metric,
            value=value,
            unit=unit,
            observed_at=snapshot.observed_at,
            labels=labels,
        )
