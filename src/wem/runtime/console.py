import json
from datetime import datetime

from wem.analysis.adaptive_baseline import AdaptiveBaselineEngine
from wem.analysis.connection_cycle import ConnectionCycleTracker
from wem.analysis.connection_cycle_slo import ConnectionCycleSloEngine
from wem.analysis.service_slo import ServiceSloEngine
from wem.collectors.networkmanager_events import NetworkManagerEventMonitor
from wem.models.metrics import DiagnosticResult, IncidentEvaluation, SensorSnapshot
from wem.runtime.sensor import (
    RuntimeConfig,
    SensorRuntime,
)
from wem.storage.baseline import BaselineRepository
from wem.storage.database import Database
from wem.storage.incidents import (
    IncidentRepository,
)
from wem.storage.repository import (
    SnapshotRepository,
)


class ConsoleSensorRuntime(SensorRuntime):
    def __init__(
        self,
        config: RuntimeConfig,
        database_path: str = "data/wem.db",
    ):
        super().__init__(config)

        self.database = Database(database_path)

        self.database.initialize()

        self.snapshot_repository = SnapshotRepository(self.database)

        self.incident_repository = IncidentRepository(self.database)
        self.baseline_repository = BaselineRepository(self.database)
        self.connection_cycle_tracker = ConnectionCycleTracker()
        self.connection_cycle_slo_engine = ConnectionCycleSloEngine(
            config.profile_config.thresholds.connection_cycle
        )
        self.adaptive_baseline_engine = AdaptiveBaselineEngine(
            config.profile_config.thresholds.adaptive_baseline
        )
        self.service_slo_engine = ServiceSloEngine(
            config.profile_config.thresholds.service_slo,
            config.profile_config.tests,
        )
        self._baseline_seeded = False
        self._baseline_ssid: str | None = None
        self.networkmanager_event_monitor = NetworkManagerEventMonitor(config.interface)
        self.networkmanager_event_monitor.start()

        self._restore_active_incidents()

    def _restore_active_incidents(
        self,
    ) -> None:
        records = self.incident_repository.active()

        for record in records:
            self.incident_engine.restore_active_incident(
                code=record.code,
                domain=record.domain,
                severity=record.severity,
                message=record.message,
                first_seen_at=(record.first_seen_at.isoformat()),
                opened_at=(record.opened_at.isoformat()),
            )

    def on_snapshot(
        self,
        snapshot: SensorSnapshot,
    ) -> None:
        snapshot.connection_cycle = self.connection_cycle_tracker.observe(
            wifi=snapshot.wifi,
            network=snapshot.network,
            connectivity=snapshot.connectivity,
            observed_at=datetime.fromisoformat(snapshot.timestamp),
            networkmanager_events=self.networkmanager_event_monitor.drain(),
            event_monitor_status=self.networkmanager_event_monitor.status,
            event_monitor_reason=self.networkmanager_event_monitor.reason,
        )

        slo_evaluation = self.connection_cycle_slo_engine.observe(snapshot.connection_cycle)
        snapshot.connection_cycle_slo = slo_evaluation.metrics
        if snapshot.diagnostic is not None and slo_evaluation.findings:
            self.diagnostic_engine.extend_result(snapshot.diagnostic, slo_evaluation.findings)

        if not self._baseline_seeded or snapshot.wifi.ssid != self._baseline_ssid:
            baseline_reference = self.baseline_repository.reference_values(
                interface=snapshot.wifi.interface,
                ssid=snapshot.wifi.ssid,
                before=datetime.fromisoformat(snapshot.timestamp),
                lookback_hours=(
                    self.config.profile_config.thresholds.adaptive_baseline.lookback_hours
                ),
                max_samples=self.config.profile_config.thresholds.adaptive_baseline.max_samples,
            )
            self.adaptive_baseline_engine.seed(snapshot.wifi.ssid, baseline_reference)
            self._baseline_ssid = snapshot.wifi.ssid
            self._baseline_seeded = True

        baseline_evaluation = self.adaptive_baseline_engine.evaluate(snapshot)
        snapshot.adaptive_baseline = baseline_evaluation.metrics
        if snapshot.diagnostic is not None and baseline_evaluation.findings:
            self.diagnostic_engine.extend_result(snapshot.diagnostic, baseline_evaluation.findings)

        service_slo_evaluation = self.service_slo_engine.evaluate(snapshot)
        snapshot.service_slo = service_slo_evaluation.metrics
        if snapshot.diagnostic is not None and service_slo_evaluation.findings:
            self.diagnostic_engine.extend_result(
                snapshot.diagnostic,
                service_slo_evaluation.findings,
            )

        slo_severity = "healthy"
        if any(item.severity == "critical" for item in slo_evaluation.findings):
            slo_severity = "critical"
        elif slo_evaluation.findings:
            slo_severity = "warning"
        slo_diagnostic = DiagnosticResult(
            overall_status=slo_severity,
            probable_domain=("connection_cycle" if slo_evaluation.findings else None),
            complete=True,
            findings=slo_evaluation.findings,
        )
        base_events = snapshot.incidents.events if snapshot.incidents is not None else []
        slo_incidents = self.incident_engine.evaluate(
            slo_diagnostic,
            timestamp=snapshot.timestamp,
            fresh_codes=slo_evaluation.fresh_codes,
        )

        baseline_severity = "healthy"
        if any(item.severity == "critical" for item in baseline_evaluation.findings):
            baseline_severity = "critical"
        elif baseline_evaluation.findings:
            baseline_severity = "warning"
        baseline_diagnostic = DiagnosticResult(
            overall_status=baseline_severity,
            probable_domain=("baseline" if baseline_evaluation.findings else None),
            complete=True,
            findings=baseline_evaluation.findings,
        )
        baseline_disabled = baseline_evaluation.metrics.status == "disabled"
        baseline_incidents = self.incident_engine.evaluate(
            baseline_diagnostic,
            timestamp=snapshot.timestamp,
            fresh_domains={"baseline"} if baseline_disabled else None,
            fresh_codes=None if baseline_disabled else baseline_evaluation.fresh_codes,
        )

        service_slo_severity = "healthy"
        if any(item.severity == "critical" for item in service_slo_evaluation.findings):
            service_slo_severity = "critical"
        elif service_slo_evaluation.findings:
            service_slo_severity = "warning"
        service_slo_diagnostic = DiagnosticResult(
            overall_status=service_slo_severity,
            probable_domain=("service_slo" if service_slo_evaluation.findings else None),
            complete=True,
            findings=service_slo_evaluation.findings,
        )
        service_slo_incidents = self.incident_engine.evaluate(
            service_slo_diagnostic,
            timestamp=snapshot.timestamp,
            fresh_codes=service_slo_evaluation.fresh_codes,
        )
        snapshot.incidents = IncidentEvaluation(
            active_incidents=service_slo_incidents.active_incidents,
            events=[
                *base_events,
                *slo_incidents.events,
                *baseline_incidents.events,
                *service_slo_incidents.events,
            ],
        )

        self.snapshot_repository.save(snapshot)

        for event in snapshot.incidents.events:
            self.incident_repository.process_event(event)

        print(
            json.dumps(
                snapshot.to_dict(),
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )

    def close(self) -> None:
        self.networkmanager_event_monitor.close()
