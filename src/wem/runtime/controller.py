import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from wem.collectors.interfaces import WirelessInterfaceDiscovery
from wem.profiles.service import ProfileService
from wem.runtime.console import ConsoleSensorRuntime
from wem.runtime.sensor import RuntimeConfig
from wem.storage.database import Database
from wem.storage.sessions import MonitoringSessionRepository


@dataclass(slots=True)
class SensorControllerConfig:
    interface: str | None = None


class SensorController:
    def __init__(
        self,
        database_path: str,
    ):
        self.database_path = database_path

        self.database = Database(database_path)
        self.database.initialize()
        self.profile_service = ProfileService(self.database)
        self.session_repository = MonitoringSessionRepository(self.database)

        self.config = SensorControllerConfig()

        self._thread: threading.Thread | None = None

        self._stop_event = threading.Event()

        self._lock = threading.Lock()

        self._running = False

        self._last_error: str | None = None
        self._started_at: str | None = None
        self._runtime_config: RuntimeConfig | None = None

    def configure(
        self,
        interface: str,
        interval_seconds: float,
    ) -> None:
        with self._lock:
            if self._running or (self._thread is not None and self._thread.is_alive()):
                raise RuntimeError("Sensor configuration cannot be changed while running.")

            self.config.interface = interface
            del interval_seconds

    def start(
        self,
    ) -> None:
        with self._lock:
            if self._running or (self._thread is not None and self._thread.is_alive()):
                raise RuntimeError("Sensor is already running.")

            if self.config.interface is None:
                raise RuntimeError("No wireless interface configured.")

            available = {item.name for item in WirelessInterfaceDiscovery().discover()}
            if self.config.interface not in available:
                raise RuntimeError("Selected interface is not an available wireless interface.")

            profile, version = self.profile_service.active()
            profile_config = self.profile_service.configuration(version)
            session = self.session_repository.start(
                interface=self.config.interface,
                profile_id=profile.id,
                profile_version_id=version.id,
            )
            self._runtime_config = RuntimeConfig(
                interface=self.config.interface,
                profile_config=profile_config,
                profile_id=profile.id,
                profile_version_id=version.id,
                profile_name=profile.name,
                profile_version=version.version,
                monitoring_session_id=session.id,
            )

            self._started_at = datetime.now(UTC).isoformat()
            self._stop_event.clear()

            self._last_error = None

            self._running = True

            self._thread = threading.Thread(
                target=self._run,
                args=(self._runtime_config,),
                name="wem-sensor-runtime",
                daemon=True,
            )

            try:
                self._thread.start()
            except Exception:
                self.session_repository.finish(session.id, "failed")
                self._running = False
                self._thread = None
                raise

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
            if thread is not None and thread.is_alive():
                return
            self._running = False
            self._thread = None

    def _run(
        self,
        runtime_config: RuntimeConfig,
    ) -> None:
        failed = False
        runtime: ConsoleSensorRuntime | None = None
        try:
            runtime = ConsoleSensorRuntime(
                runtime_config,
                database_path=self.database_path,
            )

            while not self._stop_event.is_set():
                cycle_started = time.monotonic()

                snapshot = runtime.collect_once()

                runtime.on_snapshot(snapshot)

                elapsed = time.monotonic() - cycle_started

                sleep_time = max(
                    0.0,
                    runtime_config.sampling_interval_seconds - elapsed,
                )

                self._stop_event.wait(sleep_time)

        except Exception as exc:
            failed = True
            with self._lock:
                self._last_error = str(exc)

        finally:
            if runtime is not None:
                runtime.close()

            session_error: str | None = None
            if runtime_config.monitoring_session_id is not None:
                try:
                    self.session_repository.finish(
                        runtime_config.monitoring_session_id,
                        "failed" if failed else "stopped",
                    )
                except Exception as exc:
                    session_error = str(exc)
            with self._lock:
                if session_error is not None and self._last_error is None:
                    self._last_error = session_error
                self._running = False

    def status(
        self,
    ) -> dict[str, object]:
        with self._lock:
            runtime_config = self._runtime_config
            if not self._running or runtime_config is None:
                profile, version = self.profile_service.active()
                profile_config = self.profile_service.configuration(version)
                interval_seconds = profile_config.sampling.wifi_interval_seconds
                profile_values: dict[str, object] = {
                    "session_id": None,
                    "profile_id": profile.id,
                    "profile_version_id": version.id,
                    "profile_name": profile.name,
                    "profile_version": version.version,
                }
            else:
                interval_seconds = runtime_config.sampling_interval_seconds
                profile_values = {
                    "session_id": runtime_config.monitoring_session_id,
                    "profile_id": runtime_config.profile_id,
                    "profile_version_id": runtime_config.profile_version_id,
                    "profile_name": runtime_config.profile_name,
                    "profile_version": runtime_config.profile_version,
                }
            return {
                "running": self._running,
                "started_at": self._started_at,
                "interface": (self.config.interface),
                "interval_seconds": interval_seconds,
                "last_error": (self._last_error),
                **profile_values,
            }

    @property
    def running(
        self,
    ) -> bool:
        with self._lock:
            return self._running
