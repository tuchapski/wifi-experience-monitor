from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from wifi_agent.core import Observation, ObservationKind

DEFAULT_TELEMETRY_METRICS = frozenset(
    {
        "wifi.rssi_dbm",
        "wifi.signal_avg_dbm",
        "wifi.noise_dbm",
        "wifi.snr_db",
        "wifi.tx_rate_mbps",
        "wifi.rx_rate_mbps",
        "network.gateway_latency_ms",
        "network.gateway_packet_loss_percent",
        "network.gateway_jitter_ms",
        "network.dns_latency_ms",
        "network.internet_latency_ms",
        "network.internet_packet_loss_percent",
        "network.internet_jitter_ms",
        "network.https_dns_ms",
        "network.https_tcp_connect_ms",
        "network.https_tls_handshake_ms",
        "network.https_ttfb_ms",
        "network.https_total_ms",
        "network.https_failure_elapsed_ms",
    }
)


@dataclass(frozen=True, slots=True)
class TelemetryPoint:
    observed_at: datetime
    metric: str
    value: float
    min_value: float
    max_value: float
    sample_count: int
    unit: str | None
    labels: dict[str, str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "metric": self.metric,
            "value": self.value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "sample_count": self.sample_count,
            "unit": self.unit,
            "labels": self.labels,
        }


@dataclass(slots=True)
class _Accumulator:
    total: float
    minimum: float
    maximum: float
    count: int
    observed_at: datetime
    metric: str
    unit: str | None
    labels: dict[str, str]

    def add(self, value: float, observed_at: datetime) -> None:
        self.total += value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.count += 1
        self.observed_at = max(self.observed_at, observed_at)

    def point(self) -> TelemetryPoint:
        return TelemetryPoint(
            observed_at=self.observed_at,
            metric=self.metric,
            value=self.total / self.count,
            min_value=self.minimum,
            max_value=self.maximum,
            sample_count=self.count,
            unit=self.unit,
            labels=dict(self.labels),
        )


class TelemetryAggregator:
    """Aggregate numeric gauge observations into fixed-duration rolling windows."""

    def __init__(
        self,
        window_seconds: float,
        metrics: frozenset[str] = DEFAULT_TELEMETRY_METRICS,
    ):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")
        self.window_seconds = window_seconds
        self.metrics = metrics
        self._window_started_at: datetime | None = None
        self._samples: dict[tuple[str, str | None, tuple[tuple[str, str], ...]], _Accumulator] = {}

    def consume(self, observations: list[Observation]) -> None:
        for observation in observations:
            if observation.kind is not ObservationKind.GAUGE:
                continue
            if observation.metric not in self.metrics:
                continue
            if isinstance(observation.value, bool) or not isinstance(
                observation.value, (int, float)
            ):
                continue

            if self._window_started_at is None:
                self._window_started_at = observation.observed_at

            labels_key = tuple(sorted(observation.labels.items()))
            key = (observation.metric, observation.unit, labels_key)
            value = float(observation.value)
            accumulator = self._samples.get(key)
            if accumulator is None:
                self._samples[key] = _Accumulator(
                    total=value,
                    minimum=value,
                    maximum=value,
                    count=1,
                    observed_at=observation.observed_at,
                    metric=observation.metric,
                    unit=observation.unit,
                    labels=dict(observation.labels),
                )
            else:
                accumulator.add(value, observation.observed_at)

    def flush_if_due(self, observed_at: datetime) -> list[TelemetryPoint]:
        if self._window_started_at is None:
            return []
        if observed_at - self._window_started_at < timedelta(seconds=self.window_seconds):
            return []
        return self.flush()

    def flush(self) -> list[TelemetryPoint]:
        points = [accumulator.point() for accumulator in self._samples.values()]
        points.sort(key=lambda point: (point.metric, sorted(point.labels.items())))
        self._samples.clear()
        self._window_started_at = None
        return points
