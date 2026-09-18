import re

from wem.collectors.command import run_command
from wem.models.metrics import WifiMetrics


class WifiCollector:
    def __init__(self, interface: str):
        self.interface = interface
        self.errors: list[str] = []

    def collect(self) -> WifiMetrics:
        metrics = WifiMetrics(interface=self.interface)

        self._collect_info(metrics)
        self._collect_link(metrics)
        self._collect_power_save(metrics)
        self._collect_station(metrics)

        return metrics

    def _collect_info(self, metrics: WifiMetrics) -> None:
        result = run_command(["iw", "dev", self.interface, "info"])

        if not result.success:
            self.errors.append(f"iw info failed: {result.stderr}")
            return

        output = result.stdout

        ssid_match = re.search(
            r"^\s*ssid\s+(.+)$",
            output,
            re.MULTILINE,
        )

        if ssid_match:
            metrics.ssid = ssid_match.group(1).strip()

        channel_match = re.search(
            r"channel\s+(\d+)\s+\((\d+)\s+MHz\),\s+width:\s+(\d+)\s+MHz",
            output,
        )

        if channel_match:
            metrics.channel = int(channel_match.group(1))
            metrics.frequency_mhz = int(channel_match.group(2))
            metrics.channel_width_mhz = int(channel_match.group(3))

        tx_power_match = re.search(
            r"txpower\s+([\d.]+)\s+dBm",
            output,
        )

        if tx_power_match:
            metrics.tx_power_dbm = float(tx_power_match.group(1))

    def _collect_link(self, metrics: WifiMetrics) -> None:
        result = run_command(["iw", "dev", self.interface, "link"])

        if not result.success:
            self.errors.append(f"iw link failed: {result.stderr}")
            return

        output = result.stdout

        if "Not connected." in output:
            self.errors.append(f"{self.interface} is not connected")
            return

        bssid_match = re.search(
            r"Connected to ([0-9a-fA-F:]{17})",
            output,
        )

        if bssid_match:
            metrics.bssid = bssid_match.group(1).lower()

        signal_match = re.search(
            r"signal:\s+(-?\d+)\s+dBm",
            output,
        )

        if signal_match:
            metrics.signal_dbm = int(signal_match.group(1))

        tx_match = re.search(
            r"tx bitrate:\s+([\d.]+)\s+MBit/s",
            output,
        )

        if tx_match:
            metrics.tx_bitrate_mbps = float(tx_match.group(1))

        rx_match = re.search(
            r"rx bitrate:\s+([\d.]+)\s+MBit/s",
            output,
        )

        if rx_match:
            metrics.rx_bitrate_mbps = float(rx_match.group(1))

    def _collect_power_save(self, metrics: WifiMetrics) -> None:
        result = run_command(
            [
                "iw",
                "dev",
                self.interface,
                "get",
                "power_save",
            ]
        )

        if not result.success:
            self.errors.append(f"power save check failed: {result.stderr}")
            return

        value = result.stdout.lower()

        if "on" in value:
            metrics.power_save = True
        elif "off" in value:
            metrics.power_save = False

    def _collect_station(self, metrics: WifiMetrics) -> None:
        result = run_command(
            [
                "iw",
                "dev",
                self.interface,
                "station",
                "dump",
            ]
        )

        if not result.success:
            self.errors.append(f"station dump failed: {result.stderr}")
            return

        output = result.stdout

        def get_int(pattern: str) -> int | None:
            match = re.search(
                pattern,
                output,
                re.MULTILINE,
            )

            if not match:
                return None

            return int(match.group(1))

        def get_yes_no(pattern: str) -> bool | None:
            match = re.search(
                pattern,
                output,
                re.MULTILINE,
            )

            if not match:
                return None

            return match.group(1).lower() == "yes"

        # Association state
        metrics.inactive_time_ms = get_int(r"^\s*inactive time:\s+(\d+)\s+ms")

        metrics.connected_time_seconds = get_int(r"^\s*connected time:\s+(\d+)\s+seconds")

        metrics.authorized = get_yes_no(r"^\s*authorized:\s+(yes|no)")

        metrics.authenticated = get_yes_no(r"^\s*authenticated:\s+(yes|no)")

        metrics.associated = get_yes_no(r"^\s*associated:\s+(yes|no)")

        # Signal
        metrics.signal_dbm = get_int(r"^\s*signal:\s+(-?\d+)")

        metrics.signal_avg_dbm = get_int(r"^\s*signal avg:\s+(-?\d+)")

        metrics.beacon_signal_avg_dbm = get_int(r"^\s*beacon signal avg:\s+(-?\d+)")

        # RX counters
        metrics.rx_bytes = get_int(r"^\s*rx bytes:\s+(\d+)")

        metrics.rx_packets = get_int(r"^\s*rx packets:\s+(\d+)")

        metrics.rx_drop_misc = get_int(r"^\s*rx drop misc:\s+(\d+)")

        # TX counters
        metrics.tx_bytes = get_int(r"^\s*tx bytes:\s+(\d+)")

        metrics.tx_packets = get_int(r"^\s*tx packets:\s+(\d+)")

        metrics.tx_retries = get_int(r"^\s*tx retries:\s+(\d+)")

        metrics.tx_failed = get_int(r"^\s*tx failed:\s+(\d+)")

        # Beacon counters
        metrics.beacon_loss = get_int(r"^\s*beacon loss:\s+(\d+)")

        metrics.beacon_rx = get_int(r"^\s*beacon rx:\s+(\d+)")

        metrics.dtim_period = get_int(r"^\s*DTIM period:\s+(\d+)")

        metrics.beacon_interval_ms = get_int(r"^\s*beacon interval:\s*(\d+)")

        # Wi-Fi features
        metrics.wmm_enabled = get_yes_no(r"^\s*WMM/WME:\s+(yes|no)")

        metrics.mfp_enabled = get_yes_no(r"^\s*MFP:\s+(yes|no)")

        # TX PHY information
        tx_line = re.search(
            r"^\s*tx bitrate:\s+(.+)$",
            output,
            re.MULTILINE,
        )

        if tx_line:
            self._parse_bitrate(
                tx_line.group(1),
                metrics,
                direction="tx",
            )

        # RX PHY information
        rx_line = re.search(
            r"^\s*rx bitrate:\s+(.+)$",
            output,
            re.MULTILINE,
        )

        if rx_line:
            self._parse_bitrate(
                rx_line.group(1),
                metrics,
                direction="rx",
            )

    def _parse_bitrate(
        self,
        line: str,
        metrics: WifiMetrics,
        direction: str,
    ) -> None:
        bitrate_match = re.search(
            r"([\d.]+)\s+MBit/s",
            line,
        )

        mcs_match = re.search(
            r"(?:VHT|HE|HT)-MCS\s+(\d+)",
            line,
        )

        nss_match = re.search(
            r"(?:VHT|HE)-NSS\s+(\d+)",
            line,
        )

        phy_match = re.search(
            r"\b(VHT|HE|HT)\b",
            line,
        )

        width_match = re.search(
            r"\b(20|40|80|160|320)MHz\b",
            line,
        )

        short_gi = "short GI" in line

        bitrate = float(bitrate_match.group(1)) if bitrate_match else None

        mcs = int(mcs_match.group(1)) if mcs_match else None

        nss = int(nss_match.group(1)) if nss_match else None

        phy_mode = phy_match.group(1) if phy_match else None

        if width_match:
            metrics.channel_width_mhz = int(width_match.group(1))

        if direction == "tx":
            metrics.tx_bitrate_mbps = bitrate
            metrics.tx_mcs = mcs
            metrics.tx_nss = nss
            metrics.tx_phy_mode = phy_mode
            metrics.tx_short_gi = short_gi

        elif direction == "rx":
            metrics.rx_bitrate_mbps = bitrate
            metrics.rx_mcs = mcs
            metrics.rx_nss = nss
            metrics.rx_phy_mode = phy_mode
            metrics.rx_short_gi = short_gi
