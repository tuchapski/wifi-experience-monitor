import time
from dataclasses import dataclass

from wem.analysis.wifi_delta import WifiDeltaAnalyzer
from wem.collectors.network import NetworkCollector
from wem.collectors.wifi import WifiCollector
from wem.models.metrics import SensorSnapshot, WifiMetrics
from wem.tests_engine.connectivity import ConnectivityTester


@dataclass(slots=True)
class RuntimeConfig:
    interface: str
    interval_seconds: float = 10.0

    dns_query: str = "example.com"
    internet_target: str = "1.1.1.1"
    https_url: str = "https://example.com"


class SensorRuntime:
    def __init__(self, config: RuntimeConfig):
        self.config = config

        self.previous_wifi: WifiMetrics | None = None
        self.previous_timestamp: float | None = None

        self.delta_analyzer = WifiDeltaAnalyzer()

    def collect_once(self) -> SensorSnapshot:
        started = time.monotonic()

        wifi_collector = WifiCollector(self.config.interface)

        network_collector = NetworkCollector(self.config.interface)

        wifi_metrics = wifi_collector.collect()
        network_metrics = network_collector.collect()

        connectivity_tester = ConnectivityTester(
            interface=self.config.interface,
            gateway=network_metrics.gateway,
            dns_query=self.config.dns_query,
            internet_target=self.config.internet_target,
            https_url=self.config.https_url,
        )

        connectivity_metrics = connectivity_tester.run()

        wifi_delta = None

        if self.previous_wifi is not None and self.previous_timestamp is not None:
            interval = started - self.previous_timestamp

            wifi_delta = self.delta_analyzer.calculate(
                previous=self.previous_wifi,
                current=wifi_metrics,
                interval_seconds=interval,
            )

        self.previous_wifi = wifi_metrics
        self.previous_timestamp = started

        errors = [
            *wifi_collector.errors,
            *network_collector.errors,
            *connectivity_tester.errors,
        ]

        return SensorSnapshot.create(
            wifi=wifi_metrics,
            wifi_delta=wifi_delta,
            network=network_metrics,
            connectivity=connectivity_metrics,
            errors=errors,
        )

    def run_forever(self) -> None:
        while True:
            cycle_started = time.monotonic()

            snapshot = self.collect_once()

            self.on_snapshot(snapshot)

            elapsed = time.monotonic() - cycle_started

            sleep_time = max(
                0.0,
                self.config.interval_seconds - elapsed,
            )

            time.sleep(sleep_time)

    def on_snapshot(
        self,
        snapshot: SensorSnapshot,
    ) -> None:
        raise NotImplementedError
