import json

from wem.models.metrics import SensorSnapshot
from wem.runtime.sensor import RuntimeConfig, SensorRuntime
from wem.storage.database import Database
from wem.storage.repository import SnapshotRepository


class ConsoleSensorRuntime(SensorRuntime):
    def __init__(
        self,
        config: RuntimeConfig,
        database_path: str = "data/wem.db",
    ):
        super().__init__(config)

        self.database = Database(database_path)

        self.database.initialize()

        self.repository = SnapshotRepository(self.database)

    def on_snapshot(
        self,
        snapshot: SensorSnapshot,
    ) -> None:
        self.repository.save(snapshot)

        print(
            json.dumps(
                snapshot.to_dict(),
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )
