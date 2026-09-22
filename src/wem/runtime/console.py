import json
from datetime import datetime

from wem.analysis.connection_cycle import ConnectionCycleTracker
from wem.collectors.networkmanager_events import NetworkManagerEventMonitor
from wem.models.metrics import SensorSnapshot
from wem.runtime.sensor import (
    RuntimeConfig,
    SensorRuntime,
)
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
        self.connection_cycle_tracker = ConnectionCycleTracker()
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
        self.snapshot_repository.save(snapshot)

        if snapshot.incidents is not None:
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
