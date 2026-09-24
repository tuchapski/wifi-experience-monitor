import re
from datetime import UTC, datetime

from wifi_agent.collectors.command import run_command
from wifi_agent.core import Observation, ObservationKind


class WifiStateCollector:
    def __init__(self, interface: str):
        self.interface = interface
        self.errors: list[str] = []

    def collect(self) -> list[Observation]:
        self.errors.clear()
        observed_at = datetime.now(UTC)
        values: dict[str, tuple[ObservationKind, int | float | str | bool | None, str | None]] = {
            "wifi.interface": (ObservationKind.STATE, self.interface, None)
        }

        self._collect_info(values)
        self._collect_link(values)
        self._collect_station(values)
        self._collect_survey(values)

        return [
            Observation(
                source="wifi",
                kind=kind,
                metric=metric,
                value=value,
                unit=unit,
                observed_at=observed_at,
                labels={"interface": self.interface},
            )
            for metric, (kind, value, unit) in values.items()
        ]

    def _collect_info(self, values: dict[str, tuple[ObservationKind, object, str | None]]) -> None:
        result = run_command(["iw", "dev", self.interface, "info"])
        if not result.success:
            self.errors.append(f"iw info failed: {result.stderr}")
            return

        ssid = re.search(r"^\s*ssid\s+(.+)$", result.stdout, re.MULTILINE)
        if ssid:
            values["wifi.ssid"] = (ObservationKind.STATE, ssid.group(1).strip(), None)

        channel = re.search(
            r"channel\s+(\d+)\s+\((\d+(?:\.\d+)?)\s+MHz\),\s+width:\s+(\d+(?:\.\d+)?)\s+MHz",
            result.stdout,
        )
        if channel:
            values["wifi.channel"] = (ObservationKind.STATE, int(channel.group(1)), None)
            values["wifi.frequency_mhz"] = (
                ObservationKind.STATE,
                int(float(channel.group(2))),
                "MHz",
            )
            values["wifi.channel_width_mhz"] = (
                ObservationKind.STATE,
                int(float(channel.group(3))),
                "MHz",
            )

    def _collect_link(self, values: dict[str, tuple[ObservationKind, object, str | None]]) -> None:
        result = run_command(["iw", "dev", self.interface, "link"])
        if not result.success:
            self.errors.append(f"iw link failed: {result.stderr}")
            return
        if "Not connected." in result.stdout:
            values["wifi.connected"] = (ObservationKind.STATE, False, None)
            return

        values["wifi.connected"] = (ObservationKind.STATE, True, None)
        bssid = re.search(r"Connected to ([0-9a-fA-F:]{17})", result.stdout)
        if bssid:
            values["wifi.bssid"] = (ObservationKind.STATE, bssid.group(1).lower(), None)
        ssid = re.search(r"^\s*SSID:\s+(.+)$", result.stdout, re.MULTILINE)
        if ssid:
            values["wifi.ssid"] = (ObservationKind.STATE, ssid.group(1).strip(), None)
        frequency = re.search(r"^\s*freq:\s+([\d.]+)", result.stdout, re.MULTILINE)
        if frequency:
            values["wifi.frequency_mhz"] = (
                ObservationKind.STATE,
                int(float(frequency.group(1))),
                "MHz",
            )
        signal = re.search(r"signal:\s+(-?\d+)\s+dBm", result.stdout)
        if signal:
            values["wifi.rssi_dbm"] = (ObservationKind.GAUGE, int(signal.group(1)), "dBm")
        for direction in ("tx", "rx"):
            bitrate = re.search(
                rf"^\s*{direction} bitrate:\s+([\d.]+)\s+MBit/s",
                result.stdout,
                re.MULTILINE,
            )
            if bitrate:
                values[f"wifi.{direction}_rate_mbps"] = (
                    ObservationKind.GAUGE,
                    float(bitrate.group(1)),
                    "Mbps",
                )

    def _collect_station(
        self,
        values: dict[str, tuple[ObservationKind, object, str | None]],
    ) -> None:
        if values.get("wifi.connected", (None, None, None))[1] is False:
            return
        result = run_command(["iw", "dev", self.interface, "station", "dump"])
        if not result.success:
            self.errors.append(f"station dump failed: {result.stderr}")
            return
        if not result.stdout:
            return

        for metric, pattern, unit in (
            ("wifi.signal_avg_dbm", r"^\s*signal avg:\s+(-?\d+)", "dBm"),
            ("wifi.tx_packets", r"^\s*tx packets:\s+(\d+)", None),
            ("wifi.tx_retries", r"^\s*tx retries:\s+(\d+)", None),
            ("wifi.tx_failed", r"^\s*tx failed:\s+(\d+)", None),
            ("wifi.rx_packets", r"^\s*rx packets:\s+(\d+)", None),
            ("wifi.rx_drop_misc", r"^\s*rx drop misc:\s+(\d+)", None),
        ):
            match = re.search(pattern, result.stdout, re.MULTILINE)
            if match:
                values[metric] = (ObservationKind.GAUGE, int(match.group(1)), unit)

        for direction in ("tx", "rx"):
            line = re.search(
                rf"^\s*{direction} bitrate:\s+(.+)$",
                result.stdout,
                re.MULTILINE,
            )
            if not line:
                continue
            bitrate = re.search(r"([\d.]+)\s+MBit/s", line.group(1))
            if bitrate:
                values[f"wifi.{direction}_rate_mbps"] = (
                    ObservationKind.GAUGE,
                    float(bitrate.group(1)),
                    "Mbps",
                )
            mcs = re.search(r"\b(?:(?:EHT|VHT|HE|HT)-)?MCS\s+(\d+)", line.group(1))
            if mcs:
                values[f"wifi.{direction}_mcs"] = (
                    ObservationKind.STATE,
                    int(mcs.group(1)),
                    None,
                )
            nss = re.search(r"(?:EHT|VHT|HE)-NSS\s+(\d+)", line.group(1))
            if nss:
                values[f"wifi.{direction}_nss"] = (
                    ObservationKind.STATE,
                    int(nss.group(1)),
                    None,
                )
            phy = re.search(r"\b(EHT|VHT|HE|HT)\b", line.group(1))
            if phy:
                values[f"wifi.{direction}_phy"] = (
                    ObservationKind.STATE,
                    phy.group(1),
                    None,
                )

    def _collect_survey(
        self,
        values: dict[str, tuple[ObservationKind, object, str | None]],
    ) -> None:
        if values.get("wifi.connected", (None, None, None))[1] is not True:
            return
        frequency_entry = values.get("wifi.frequency_mhz")
        if frequency_entry is None:
            return
        frequency = frequency_entry[1]

        result = run_command(["iw", "dev", self.interface, "survey", "dump"])
        if not result.success:
            return
        blocks = re.split(r"(?=^\s*Survey data from )", result.stdout, flags=re.MULTILINE)
        for block in blocks:
            in_use = re.search(r"^\s*frequency:\s+(\d+)\s+MHz\s+\[in use\]", block, re.MULTILINE)
            if not in_use or int(in_use.group(1)) != frequency:
                continue

            for metric, pattern in (
                ("wifi.survey_active_ms", r"^\s*channel active time:\s+(\d+)\s+ms\s*$"),
                ("wifi.survey_busy_ms", r"^\s*channel busy time:\s+(\d+)\s+ms\s*$"),
                ("wifi.survey_rx_ms", r"^\s*channel receive time:\s+(\d+)\s+ms\s*$"),
                ("wifi.survey_tx_ms", r"^\s*channel transmit time:\s+(\d+)\s+ms\s*$"),
            ):
                match = re.search(pattern, block, re.MULTILINE)
                if match:
                    values[metric] = (
                        ObservationKind.GAUGE,
                        int(match.group(1)),
                        "ms",
                    )

            noise = re.search(r"^\s*noise:\s+(-?\d+)\s+dBm\s*$", block, re.MULTILINE)
            if noise:
                noise_dbm = int(noise.group(1))
                values["wifi.noise_dbm"] = (ObservationKind.GAUGE, noise_dbm, "dBm")
                rssi_entry = values.get("wifi.rssi_dbm")
                if rssi_entry is not None and isinstance(rssi_entry[1], (int, float)):
                    values["wifi.snr_db"] = (
                        ObservationKind.GAUGE,
                        float(rssi_entry[1]) - noise_dbm,
                        "dB",
                    )
            return
