import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

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
from wem.models.metrics import (
    MonitoringContext,
    ProfileReference,
    SensorSnapshot,
    WifiMetrics,
)
from wem.profiles.defaults import default_profile_config
from wem.profiles.models import TestProfileConfig
from wem.runtime.connectivity_scheduler import ConnectivityTestScheduler
from wem.tests_engine.connectivity import ConnectivityTester


@dataclass(slots=True)
class RuntimeConfig:
    interface: str
    interval_seconds: float | None = None
    profile_config: TestProfileConfig = field(default_factory=default_profile_config)
    profile_id: int | None = None
    profile_version_id: int | None = None
    profile_name: str | None = None
    profile_version: int | None = None
    monitoring_session_id: int | None = None

    def __post_init__(self) -> None:
        self.profile_config = self.profile_config.model_copy(deep=True)
        if self.interval_seconds is not None:
            self.profile_config.sampling.wifi_interval_seconds = self.interval_seconds
            for name in ("gateway", "dns", "internet", "https"):
                getattr(self.profile_config.tests, name).interval_seconds = self.interval_seconds

    @property
    def sampling_interval_seconds(self) -> float:
        return self.profile_config.sampling.wifi_interval_seconds


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
        self.diagnostic_engine = DiagnosticEngine(self.config.profile_config)
        self.incident_engine = IncidentEngine()
        self.connectivity_scheduler = ConnectivityTestScheduler(self.config.profile_config.tests)

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
            tests=self.config.profile_config.tests,
        )

        blocked = (
            health_metrics.interface_exists is not True
            or health_metrics.wireless_interface is not True
            or health_metrics.interface_up is False
            or health_metrics.rfkill_soft_blocked is True
            or health_metrics.rfkill_hard_blocked is True
            or wifi_metrics.associated is False
        )
        scheduled = self.connectivity_scheduler.collect(
            connectivity_tester,
            now=started,
            observed_at=datetime.now(UTC).isoformat(),
            blocked=blocked,
            gateway=network_metrics.gateway,
        )
        connectivity_metrics = scheduled.metrics

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

        incident_evaluation = self.incident_engine.evaluate(
            diagnostic=diagnostic,
            fresh_domains={"wifi", "sensor", *scheduled.fresh_domains},
        )

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
            monitoring=self._monitoring_context(),
        )

    def _monitoring_context(self) -> MonitoringContext | None:
        session_id = self.config.monitoring_session_id
        profile_id = self.config.profile_id
        profile_version_id = self.config.profile_version_id
        profile_name = self.config.profile_name
        profile_version = self.config.profile_version
        if (
            session_id is None
            or profile_id is None
            or profile_version_id is None
            or profile_name is None
            or profile_version is None
        ):
            return None
        return MonitoringContext(
            session_id=session_id,
            profile=ProfileReference(
                profile_id=profile_id,
                profile_version_id=profile_version_id,
                name=profile_name,
                version=profile_version,
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
                self.config.sampling_interval_seconds - elapsed,
            )

            time.sleep(sleep_time)

    def on_snapshot(
        self,
        snapshot: SensorSnapshot,
    ) -> None:
        raise NotImplementedError
