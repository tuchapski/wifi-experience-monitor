import time
from dataclasses import dataclass

from wem.analysis.environment import EnvironmentChangeAnalyzer
from wem.analysis.experience import ExperienceScoreEngine
from wem.analysis.recommendations import RecommendationEngine
from wem.analysis.wifi_delta import WifiDeltaAnalyzer
from wem.calibration.engine import CalibrationEngine
from wem.collectors.health import SensorHealthCollector
from wem.collectors.network import NetworkCollector
from wem.collectors.wifi import WifiCollector
from wem.diagnostics.engine import DiagnosticEngine
from wem.incidents.engine import IncidentEngine
from wem.models.metrics import ConnectivityMetrics, SensorSnapshot, TestOutcome, WifiMetrics
from wem.tests_engine.connectivity import ConnectivityTester


@dataclass(slots=True)
class RuntimeConfig:
    interface: str
    interval_seconds: float = 10.0

    dns_query: str = "example.com"
    internet_target: str = "1.1.1.1"
    https_url: str = "https://example.com"


class SensorRuntime:
    def __init__(
        self,
        config: RuntimeConfig,
    ):
        self.config = config

        self.previous_wifi: WifiMetrics | None = None
        self.previous_timestamp: float | None = None

        self.delta_analyzer = WifiDeltaAnalyzer()
        self.experience_engine = ExperienceScoreEngine()
        self.environment_analyzer = EnvironmentChangeAnalyzer()
        self.recommendation_engine = RecommendationEngine()
        self.calibration_engine = CalibrationEngine()
        self.diagnostic_engine = DiagnosticEngine()
        self.incident_engine = IncidentEngine()

    def collect_once(
        self,
    ) -> SensorSnapshot:
        started = time.monotonic()

        health_collector = SensorHealthCollector(self.config.interface)

        wifi_collector = WifiCollector(self.config.interface)

        network_collector = NetworkCollector(self.config.interface)

        health_metrics = health_collector.collect()

        calibration = self.calibration_engine.analyze(health_metrics)

        wifi_metrics = wifi_collector.collect()
        network_metrics = network_collector.collect()

        connectivity_tester = ConnectivityTester(
            interface=self.config.interface,
            gateway=network_metrics.gateway,
            dns_query=self.config.dns_query,
            internet_target=self.config.internet_target,
            https_url=self.config.https_url,
        )

        blocked = (
            health_metrics.interface_exists is not True
            or health_metrics.wireless_interface is not True
            or health_metrics.interface_up is False
            or health_metrics.rfkill_soft_blocked is True
            or health_metrics.rfkill_hard_blocked is True
            or wifi_metrics.associated is False
        )
        if blocked:
            connectivity_metrics = ConnectivityMetrics(
                tests={
                    name: TestOutcome(
                        "skipped",
                        "Interface unavailable, unverified, blocked or disconnected.",
                        "host" if name in {"dns", "https"} else "selected_interface",
                    )
                    for name in ("gateway", "internet", "dns", "https")
                }
            )
        else:
            connectivity_metrics = connectivity_tester.run()

        wifi_delta = None
        environment_changes = []

        if self.previous_wifi is not None and self.previous_timestamp is not None:
            interval = started - self.previous_timestamp

            wifi_delta = self.delta_analyzer.calculate(
                previous=self.previous_wifi,
                current=wifi_metrics,
                interval_seconds=interval,
            )

            environment_changes = self.environment_analyzer.compare(
                previous=self.previous_wifi,
                current=wifi_metrics,
            )

        errors = [
            *health_collector.errors,
            *wifi_collector.errors,
            *network_collector.errors,
            *connectivity_tester.errors,
        ]

        diagnostic = self.diagnostic_engine.analyze(
            wifi=wifi_metrics,
            wifi_delta=wifi_delta,
            connectivity=connectivity_metrics,
            calibration=calibration,
            collector_errors=errors,
        )

        incident_evaluation = self.incident_engine.evaluate(diagnostic=diagnostic)

        recommendations = self.recommendation_engine.build(
            diagnostic=diagnostic,
            calibration=calibration,
            wifi=wifi_metrics,
            wifi_delta=wifi_delta,
            connectivity=connectivity_metrics,
            environment_changes=environment_changes,
        )

        self.previous_wifi = wifi_metrics
        self.previous_timestamp = started

        return SensorSnapshot.create(
            health=health_metrics,
            calibration=calibration,
            wifi=wifi_metrics,
            wifi_delta=wifi_delta,
            network=network_metrics,
            connectivity=connectivity_metrics,
            diagnostic=diagnostic,
            incidents=incident_evaluation,
            environment_changes=environment_changes,
            recommendations=recommendations,
            errors=errors,
            experience_score=self.experience_engine.calculate(
                wifi_metrics, wifi_delta, connectivity_metrics, calibration, errors
            ),
        )

    def run_forever(
        self,
    ) -> None:
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
