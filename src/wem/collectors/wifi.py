import re

from wem.collectors.command import run_command
from wem.models.metrics import WifiMetrics


class WifiCollector:
    def __init__(self, interface: str):
        self.interface = interface
        self.errors: list[str] = []

    def collect(self) -> WifiMetrics:
        self.errors.clear()
        metrics = WifiMetrics(interface=self.interface)

        self._collect_info(metrics)
        self._collect_link(metrics)
        self._collect_power_save(metrics)
        self._collect_station(metrics)
        self._collect_survey(metrics)

        return metrics

    def _collect_survey(self, metrics: WifiMetrics) -> None:
        survey = metrics.survey
        if metrics.associated is not True or metrics.frequency_mhz is None:
            survey.reason = "Association and operating frequency are required."
            return

        result = run_command(["iw", "dev", self.interface, "survey", "dump"])
        if not result.success:
            unsupported = "not supported" in result.stderr.lower() or "(-95)" in result.stderr
            survey.status = "unsupported" if unsupported else "error"
            survey.reason = result.stderr.strip() or "Unable to read optional survey data."
            # Optional telemetry must not become evidence of a connectivity failure.
            return

        blocks = re.split(r"(?=^\s*Survey data from )", result.stdout, flags=re.MULTILINE)
        in_use = [
            block
            for block in blocks
            if re.search(r"^\s*frequency:.*\[in use\]", block, re.MULTILINE)
        ]
        if len(in_use) != 1:
            survey.reason = "No unique in-use channel in the driver's survey output."
            return
        output = in_use[0]
        frequency = re.search(r"^\s*frequency:\s+(\d+)\s+MHz", output, re.MULTILINE)
        if frequency is None or int(frequency.group(1)) != metrics.frequency_mhz:
            survey.reason = "Survey channel does not match the observed Wi-Fi frequency."
            return
        survey.frequency_mhz = int(frequency.group(1))

        noise = re.search(r"^\s*noise:\s+(-?\d+)\s+dBm\s*$", output, re.MULTILINE)
        if noise and -127 <= int(noise.group(1)) < 0:
            survey.noise_dbm = int(noise.group(1))
            if metrics.signal_dbm is not None:
                survey.snr_db = metrics.signal_dbm - survey.noise_dbm

        for label, attribute in (
            ("active", "active_ms"),
            ("busy", "busy_ms"),
            ("receive", "rx_ms"),
            ("transmit", "tx_ms"),
        ):
            match = re.search(rf"^\s*channel {label} time:\s+(\d+)\s+ms\s*$", output, re.MULTILINE)
            if match:
                setattr(survey, attribute, int(match.group(1)))

        values = (survey.noise_dbm, survey.active_ms, survey.busy_ms, survey.rx_ms, survey.tx_ms)
        if all(value is not None for value in values):
            survey.status = "available"
            survey.reason = "In-use channel survey reported by the driver."
        elif any(value is not None for value in values):
            survey.status = "partial"
            survey.reason = "Partial driver support; unreported measurements remain unavailable."
        else:
            survey.reason = "Driver returned a channel but no usable noise or time counters."

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
            r"channel\s+(\d+)\s+\((\d+(?:\.\d+)?)\s+MHz\),\s+width:\s+(\d+(?:\.\d+)?)\s+MHz",
            output,
        )

        if channel_match:
            metrics.channel = int(channel_match.group(1))
            metrics.frequency_mhz = int(float(channel_match.group(2)))
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
            metrics.associated = False
            self.errors.append(f"{self.interface} is not connected")
            return

        bssid_match = re.search(
            r"Connected to ([0-9a-fA-F:]{17})",
            output,
        )

        if bssid_match:
            metrics.bssid = bssid_match.group(1).lower()
            metrics.associated = True

        ssid_match = re.search(r"^\s*SSID:\s+(.+)$", output, re.MULTILINE)
        if ssid_match:
            metrics.ssid = ssid_match.group(1).strip()
        frequency_match = re.search(r"^\s*freq:\s+([\d.]+)", output, re.MULTILINE)
        if frequency_match:
            metrics.frequency_mhz = int(float(frequency_match.group(1)))

        signal_match = re.search(
            r"signal:\s+(-?\d+)\s+dBm",
            output,
        )

        if signal_match:
            metrics.signal_dbm = int(signal_match.group(1))

        for direction in ("tx", "rx"):
            match = re.search(rf"^\s*{direction} bitrate:\s+(.+)$", output, re.MULTILINE)
            if match:
                self._parse_bitrate(match.group(1), metrics, direction)

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
        if metrics.associated is False or not output.strip():
            return
        stations = re.split(r"(?=^Station )", output, flags=re.MULTILINE)
        stations = [block for block in stations if block.strip()]
        if metrics.bssid is not None:
            matching = [
                block for block in stations if block.lower().startswith(f"station {metrics.bssid} ")
            ]
            if not matching:
                self.errors.append("station dump did not contain the associated BSSID")
                return
            output = matching[0]
        elif len(stations) > 1:
            self.errors.append("station dump is ambiguous without an associated BSSID")
            return

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

        associated = get_yes_no(r"^\s*associated:\s+(yes|no)")
        if associated is not None:
            metrics.associated = associated

        # Signal
        signal = get_int(r"^\s*signal:\s+(-?\d+)")
        if signal is not None:
            metrics.signal_dbm = signal

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

        if bitrate_match is None:
            return

        mcs_match = re.search(
            r"\b(?:(?:EHT|VHT|HE|HT)-)?MCS\s+(\d+)",
            line,
        )

        nss_match = re.search(
            r"(?:EHT|VHT|HE)-NSS\s+(\d+)",
            line,
        )

        phy_match = re.search(
            r"\b(EHT|VHT|HE|HT)\b",
            line,
        )

        width_match = re.search(
            r"\b(20|40|80|160|320)\s*MHz\b",
            line,
        )

        short_gi = None

        bitrate = float(bitrate_match.group(1)) if bitrate_match else None

        mcs = int(mcs_match.group(1)) if mcs_match else None

        nss = int(nss_match.group(1)) if nss_match else None

        phy_mode = phy_match.group(1) if phy_match else ("HT" if mcs_match else None)
        if phy_mode in {"HT", "VHT"}:
            short_gi = "short GI" in line

        # Interface operating width and the width of a reported TX/RX rate differ.
        width = int(width_match.group(1)) if width_match else None
        setattr(metrics, f"{direction}_channel_width_mhz", width)

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
