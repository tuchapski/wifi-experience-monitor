import json

from wem.models.metrics import SensorSnapshot
from wem.runtime.sensor import SensorRuntime


class ConsoleSensorRuntime(SensorRuntime):
    def on_snapshot(
        self,
        snapshot: SensorSnapshot,
    ) -> None:
        print(
            json.dumps(
                snapshot.to_dict(),
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )
