import threading
import time
from dataclasses import dataclass

from wem.runtime.console import ConsoleSensorRuntime
from wem.runtime.sensor import RuntimeConfig


@dataclass(slots=True)
class SensorControllerConfig:
    interface: str | None = None

    interval_seconds: float = 5.0


class SensorController:
    def __init__(
        self,
        database_path: str,
    ):
        self.database_path = database_path

        self.config = SensorControllerConfig()

        self._thread: threading.Thread | None = None

        self._stop_event = threading.Event()

        self._lock = threading.Lock()

        self._running = False

        self._last_error: str | None = None

    def configure(
        self,
        interface: str,
        interval_seconds: float,
    ) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("Sensor configuration cannot be changed while running.")

            self.config.interface = interface
            self.config.interval_seconds = interval_seconds

    def start(
        self,
    ) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("Sensor is already running.")

            if self.config.interface is None:
                raise RuntimeError("No wireless interface configured.")

            self._stop_event.clear()

            self._last_error = None

            self._running = True

            self._thread = threading.Thread(
                target=self._run,
                name="wem-sensor-runtime",
                daemon=True,
            )

            self._thread.start()

    def stop(
        self,
    ) -> None:
        with self._lock:
            if not self._running:
                return

            self._stop_event.set()

            thread = self._thread

        if thread is not None:
            thread.join(timeout=15.0)

        with self._lock:
            self._running = False

            self._thread = None

    def _run(
        self,
    ) -> None:
        interface = self.config.interface

        if interface is None:
            with self._lock:
                self._running = False

            return

        runtime = ConsoleSensorRuntime(
            RuntimeConfig(
                interface=interface,
                interval_seconds=(self.config.interval_seconds),
            ),
            database_path=self.database_path,
        )

        try:
            while not self._stop_event.is_set():
                cycle_started = time.monotonic()

                snapshot = runtime.collect_once()

                runtime.on_snapshot(snapshot)

                elapsed = time.monotonic() - cycle_started

                sleep_time = max(
                    0.0,
                    self.config.interval_seconds - elapsed,
                )

                self._stop_event.wait(sleep_time)

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)

        finally:
            with self._lock:
                self._running = False

    def status(
        self,
    ) -> dict[str, object]:
        with self._lock:
            return {
                "running": self._running,
                "interface": (self.config.interface),
                "interval_seconds": (self.config.interval_seconds),
                "last_error": (self._last_error),
            }

    @property
    def running(
        self,
    ) -> bool:
        with self._lock:
            return self._running
