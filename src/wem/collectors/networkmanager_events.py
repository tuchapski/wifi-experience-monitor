from __future__ import annotations

import re
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

_NM_SERVICE: Final = "org.freedesktop.NetworkManager"
_NM_ROOT: Final = "/org/freedesktop/NetworkManager"

_STATE_NAMES = {
    0: "unknown",
    10: "unmanaged",
    20: "unavailable",
    30: "disconnected",
    40: "prepare",
    50: "config",
    60: "need_auth",
    70: "ip_config",
    80: "ip_check",
    90: "secondaries",
    100: "activated",
    110: "deactivating",
    120: "failed",
}

_DEVICE_PATH_RE = re.compile(r"(/org/freedesktop/NetworkManager/Devices/\d+)")
_STATE_CHANGED_RE = re.compile(
    r"StateChanged\s*\(\s*(?:uint32\s+)?(\d+)\s*,\s*"
    r"(?:uint32\s+)?(\d+)\s*,\s*(?:uint32\s+)?(\d+)\s*,?\s*\)"
)


def networkmanager_state_name(state: int | None) -> str | None:
    if state is None:
        return None
    return _STATE_NAMES.get(state, f"state_{state}")


@dataclass(frozen=True, slots=True)
class NetworkManagerDeviceEvent:
    observed_at: datetime
    new_state: int
    old_state: int
    reason: int

    @property
    def new_state_name(self) -> str:
        return networkmanager_state_name(self.new_state) or "unknown"


class NetworkManagerEventMonitor:
    """Observe NetworkManager device StateChanged signals without a Python D-Bus dependency.

    ``gdbus`` connects to the system bus and emits each Device.StateChanged signal as it
    arrives. Timestamps are assigned when the sensor receives the signal. Failure to start
    the monitor is non-fatal; the connection-cycle tracker keeps its sampling fallback.
    """

    def __init__(self, interface: str):
        self.interface = interface
        self._events: deque[NetworkManagerDeviceEvent] = deque(maxlen=256)
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._closing = False
        self._status = "not_started"
        self._reason: str | None = None
        self._device_path: str | None = None

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    @property
    def device_path(self) -> str | None:
        with self._lock:
            return self._device_path

    def start(self) -> None:
        gdbus = shutil.which("gdbus")
        if gdbus is None:
            self._set_status(
                "unavailable",
                "gdbus is not installed; connection-cycle timing falls back to sampling.",
            )
            return

        try:
            result = subprocess.run(
                [
                    gdbus,
                    "call",
                    "--system",
                    "--dest",
                    _NM_SERVICE,
                    "--object-path",
                    _NM_ROOT,
                    "--method",
                    f"{_NM_SERVICE}.GetDeviceByIpIface",
                    self.interface,
                ],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._set_status("unavailable", f"Unable to query NetworkManager D-Bus: {exc}")
            return

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown D-Bus error"
            self._set_status("unavailable", f"NetworkManager device lookup failed: {detail}")
            return

        device_path = self.parse_device_path(result.stdout)
        if device_path is None:
            self._set_status(
                "unavailable",
                "NetworkManager did not return a D-Bus device path for the selected interface.",
            )
            return

        try:
            process = subprocess.Popen(
                [
                    gdbus,
                    "monitor",
                    "--system",
                    "--dest",
                    _NM_SERVICE,
                    "--object-path",
                    device_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self._set_status("unavailable", f"Unable to start NetworkManager D-Bus monitor: {exc}")
            return

        with self._lock:
            self._process = process
            self._device_path = device_path
            self._closing = False
            self._status = "active"
            self._reason = None

        thread = threading.Thread(
            target=self._read_loop,
            args=(process,),
            name=f"wem-nm-dbus-{self.interface}",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def drain(self) -> list[NetworkManagerDeviceEvent]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    def close(self) -> None:
        with self._lock:
            self._closing = True
            process = self._process
            thread = self._thread

        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lock:
            self._process = None
            self._thread = None
            if self._status == "active":
                self._status = "stopped"

    def _read_loop(self, process: subprocess.Popen[str]) -> None:
        stdout = process.stdout
        if stdout is None:
            self._set_status("error", "gdbus monitor started without a stdout stream.")
            return

        for line in stdout:
            event = self.parse_state_changed(line)
            if event is not None:
                with self._lock:
                    self._events.append(event)

        return_code = process.wait()
        with self._lock:
            closing = self._closing

        if closing:
            return

        stderr = process.stderr.read().strip() if process.stderr is not None else ""
        detail = stderr or f"gdbus monitor exited with status {return_code}."
        self._set_status("error", detail)

    @staticmethod
    def parse_device_path(output: str) -> str | None:
        match = _DEVICE_PATH_RE.search(output)
        return match.group(1) if match is not None else None

    @staticmethod
    def parse_state_changed(
        line: str,
        *,
        observed_at: datetime | None = None,
    ) -> NetworkManagerDeviceEvent | None:
        if ".Device.StateChanged" not in line:
            return None
        match = _STATE_CHANGED_RE.search(line)
        if match is None:
            return None

        timestamp = observed_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        else:
            timestamp = timestamp.astimezone(UTC)

        return NetworkManagerDeviceEvent(
            observed_at=timestamp,
            new_state=int(match.group(1)),
            old_state=int(match.group(2)),
            reason=int(match.group(3)),
        )

    def _set_status(self, status: str, reason: str | None) -> None:
        with self._lock:
            self._status = status
            self._reason = reason
