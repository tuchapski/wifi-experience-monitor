import re
from pathlib import Path

from wem.collectors.command import run_command
from wem.models.metrics import SensorHealthMetrics


class SensorHealthCollector:
    def __init__(
        self,
        interface: str,
    ):
        self.interface = interface

        self.errors: list[str] = []

    def collect(
        self,
    ) -> SensorHealthMetrics:
        metrics = SensorHealthMetrics(interface=self.interface)

        self._collect_interface_state(metrics)

        self._collect_wireless_state(metrics)

        self._collect_driver(metrics)

        self._collect_rfkill(metrics)

        self._collect_network_manager(metrics)

        self._collect_kernel(metrics)

        return metrics

    def _collect_interface_state(
        self,
        metrics: SensorHealthMetrics,
    ) -> None:
        result = run_command(
            [
                "ip",
                "-o",
                "link",
                "show",
                "dev",
                self.interface,
            ]
        )

        if not result.success:
            metrics.interface_exists = (
                False
                if "does not exist" in result.stderr or "Cannot find device" in result.stderr
                else None
            )

            self.errors.append("Unable to read interface state")

            return

        metrics.interface_exists = True

        output = result.stdout

        flags_match = re.search(
            r"<([^>]+)>",
            output,
        )

        if flags_match is None:
            metrics.interface_up = None

            return

        flags = {item.strip() for item in flags_match.group(1).split(",")}

        metrics.interface_up = "UP" in flags

    def _collect_wireless_state(
        self,
        metrics: SensorHealthMetrics,
    ) -> None:
        result = run_command(
            [
                "iw",
                "dev",
                self.interface,
                "info",
            ]
        )

        if not result.success:
            metrics.wireless_interface = None

            self.errors.append("Interface was not recognized by iw")

            return

        metrics.wireless_interface = True

        power_result = run_command(
            [
                "iw",
                "dev",
                self.interface,
                "get",
                "power_save",
            ]
        )

        if not power_result.success:
            return

        output = power_result.stdout.strip().lower()

        if "on" in output:
            metrics.power_save = True

        elif "off" in output:
            metrics.power_save = False

    def _collect_driver(
        self,
        metrics: SensorHealthMetrics,
    ) -> None:
        result = run_command(
            [
                "ethtool",
                "-i",
                self.interface,
            ]
        )

        if not result.success:
            self.errors.append("Unable to read Wi-Fi driver information")

            return

        for line in result.stdout.splitlines():
            key, separator, value = line.partition(":")

            if not separator:
                continue

            key = key.strip().lower()
            value = value.strip()

            if key == "driver":
                metrics.driver = value or None

            elif key == "firmware-version":
                metrics.firmware_version = value or None

    def _collect_rfkill(
        self,
        metrics: SensorHealthMetrics,
    ) -> None:
        # Restrict rfkill evidence to the radio backing the selected interface.
        radio = Path("/sys/class/net") / self.interface / "phy80211"
        try:
            entries = list(radio.glob("rfkill*"))
            if len(entries) != 1:
                return
            for filename, attribute in (
                ("soft", "rfkill_soft_blocked"),
                ("hard", "rfkill_hard_blocked"),
            ):
                value = (entries[0] / filename).read_text().strip()
                if value in {"0", "1"}:
                    setattr(metrics, attribute, value == "1")
        except OSError as exc:
            self.errors.append(f"Unable to read radio block state: {exc}")

    def _collect_network_manager(
        self,
        metrics: SensorHealthMetrics,
    ) -> None:
        result = run_command(
            [
                "nmcli",
                "-t",
                "-f",
                "GENERAL.STATE,GENERAL.NM-MANAGED",
                "device",
                "show",
                self.interface,
            ]
        )

        if not result.success:
            return

        for line in result.stdout.splitlines():
            key, separator, value = line.partition(":")

            if not separator:
                continue

            key = key.strip()
            value = value.strip()

            if key == "GENERAL.STATE":
                metrics.network_manager_state = value or None

            elif key == "GENERAL.NM-MANAGED":
                lowered = value.lower()

                if lowered in {
                    "yes",
                    "true",
                }:
                    metrics.network_manager_managed = True

                elif lowered in {
                    "no",
                    "false",
                }:
                    metrics.network_manager_managed = False

    def _collect_kernel(
        self,
        metrics: SensorHealthMetrics,
    ) -> None:
        result = run_command(
            [
                "uname",
                "-r",
            ]
        )

        if result.success:
            metrics.kernel_version = result.stdout.strip() or None
