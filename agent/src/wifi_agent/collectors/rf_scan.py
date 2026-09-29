import re
from datetime import UTC, datetime
from time import monotonic

from wifi_agent.collectors.command import run_command
from wifi_agent.core.rf import BssObservation, RfScanResult, WifiBand

_BSS_HEADER = re.compile(
    r"^BSS[ \t]+([0-9a-fA-F:]{17})[ \t]*(?:\(on[ \t]+([^)]+)\))?"
    r"(?:[ \t]+--[ \t]+(.*))?$",
    re.MULTILINE,
)


def frequency_to_band(frequency_mhz: int) -> WifiBand:
    if 2400 <= frequency_mhz < 2500:
        return "2.4ghz"
    if 4900 <= frequency_mhz < 5925:
        return "5ghz"
    if 5925 <= frequency_mhz <= 7125:
        return "6ghz"
    return "unknown"


def frequency_to_channel(frequency_mhz: int) -> int | None:
    """Map common 2.4/5/6 GHz center frequencies to IEEE channel numbers."""

    if frequency_mhz == 2484:
        return 14
    if 2412 <= frequency_mhz <= 2472 and (frequency_mhz - 2407) % 5 == 0:
        return (frequency_mhz - 2407) // 5
    if 5000 <= frequency_mhz < 5925 and (frequency_mhz - 5000) % 5 == 0:
        return (frequency_mhz - 5000) // 5
    if frequency_mhz == 5935:
        return 2
    if 5955 <= frequency_mhz <= 7115 and (frequency_mhz - 5950) % 5 == 0:
        return (frequency_mhz - 5950) // 5
    return None


def _match_int(block: str, pattern: str) -> int | None:
    match = re.search(pattern, block, re.MULTILINE | re.IGNORECASE)
    return int(match.group(1)) if match else None


def _parse_channel_width(block: str) -> int | None:
    explicit = re.search(
        r"channel width:\s*\d+\s*\((20|40|80|160|320)\s*MHz\)",
        block,
        re.IGNORECASE,
    )
    if explicit:
        return int(explicit.group(1))

    explicit = re.search(r"\bwidth:\s*(20|40|80|160|320)\s*MHz\b", block, re.IGNORECASE)
    if explicit:
        return int(explicit.group(1))

    secondary = re.search(
        r"secondary channel offset:\s*(above|below|no secondary)",
        block,
        re.IGNORECASE,
    )
    if secondary:
        return 20 if secondary.group(1).lower() == "no secondary" else 40
    return None


def _parse_phy_capabilities(block: str) -> tuple[str, ...]:
    capabilities: list[str] = []
    for phy in ("HT", "VHT", "HE", "EHT"):
        if re.search(
            rf"^[ \t]*{phy}[ \t]+(?:capabilities|operation|Iftypes)\b",
            block,
            re.MULTILINE,
        ):
            capabilities.append(phy)
    return tuple(capabilities)


def _parse_security(block: str) -> tuple[str, ...]:
    security: list[str] = []
    if re.search(r"^[ \t]*RSN:[ \t]*$", block, re.MULTILINE):
        security.append("RSN")
    if re.search(r"^[ \t]*WPA:[ \t]*$", block, re.MULTILINE):
        security.append("WPA")
    return tuple(security)


def _parse_bss_block(block: str, fallback_interface: str) -> BssObservation | None:
    header = _BSS_HEADER.search(block)
    if not header:
        return None

    frequency = re.search(r"^[ \t]*freq:[ \t]*([\d.]+)[ \t]*$", block, re.MULTILINE)
    if not frequency:
        return None
    frequency_mhz = int(round(float(frequency.group(1))))

    ssid = re.search(r"^[ \t]*SSID:[ \t]*(.*)$", block, re.MULTILINE)
    signal = re.search(r"^[ \t]*signal:[ \t]*(-?[\d.]+)[ \t]*dBm[ \t]*$", block, re.MULTILINE)
    capability = re.search(r"^[ \t]*capability:[ \t]*(.+)$", block, re.MULTILINE)
    capability_text = capability.group(1).strip() if capability else None
    associated_marker = header.group(3) or ""

    primary_channel = _match_int(block, r"^[ \t]*\*?[ \t]*primary channel:[ \t]*(\d+)[ \t]*$")
    ds_channel = _match_int(block, r"^[ \t]*DS Parameter set:[ \t]*channel[ \t]+(\d+)[ \t]*$")

    bss_load_utilization = _match_int(
        block,
        r"^[ \t]*\*?[ \t]*channel utili[sz]ation:[ \t]*(\d+)[ \t]*/[ \t]*255[ \t]*$",
    )

    return BssObservation(
        bssid=header.group(1).lower(),
        interface=(header.group(2) or fallback_interface).strip(),
        ssid=ssid.group(1).strip() or None if ssid else None,
        frequency_mhz=frequency_mhz,
        channel=primary_channel or ds_channel or frequency_to_channel(frequency_mhz),
        band=frequency_to_band(frequency_mhz),
        rssi_dbm=float(signal.group(1)) if signal else None,
        associated="associated" in associated_marker.lower(),
        channel_width_mhz=_parse_channel_width(block),
        beacon_interval_tu=_match_int(
            block,
            r"^[ \t]*beacon interval:[ \t]*(\d+)[ \t]*TUs?[ \t]*$",
        ),
        capability=capability_text,
        privacy=bool(capability_text and re.search(r"\bPrivacy\b", capability_text)),
        security=_parse_security(block),
        phy_capabilities=_parse_phy_capabilities(block),
        bss_load_station_count=_match_int(
            block,
            r"^[ \t]*\*?[ \t]*station count:[ \t]*(\d+)[ \t]*$",
        ),
        bss_load_channel_utilization_raw=bss_load_utilization,
        last_seen_ms=_match_int(block, r"^[ \t]*last seen:[ \t]*(\d+)[ \t]*ms ago[ \t]*$"),
    )


def parse_iw_scan(output: str, interface: str) -> tuple[BssObservation, ...]:
    """Parse ``iw dev <interface> scan`` output without inventing unavailable fields."""

    starts = [match.start() for match in _BSS_HEADER.finditer(output)]
    if not starts:
        return ()

    blocks = [
        output[start : starts[index + 1] if index + 1 < len(starts) else len(output)]
        for index, start in enumerate(starts)
    ]
    parsed = (_parse_bss_block(block, interface) for block in blocks)
    return tuple(bss for bss in parsed if bss is not None)


class RfScanCollector:
    """Run one foreground scan. Scheduling and persistence belong to later P0.1 stages."""

    def __init__(self, interface: str, timeout_seconds: float = 15.0):
        self.interface = interface
        self.timeout_seconds = timeout_seconds

    def collect(self) -> RfScanResult:
        started = monotonic()
        result = run_command(
            ["iw", "dev", self.interface, "scan"],
            timeout=self.timeout_seconds,
        )
        duration_ms = (monotonic() - started) * 1000
        observed_at = datetime.now(UTC)
        if not result.success:
            detail = result.stderr or f"exit code {result.returncode}"
            return RfScanResult(
                interface=self.interface,
                observed_at=observed_at,
                duration_ms=duration_ms,
                error=f"iw scan failed: {detail}",
            )

        return RfScanResult(
            interface=self.interface,
            observed_at=observed_at,
            duration_ms=duration_ms,
            bsses=parse_iw_scan(result.stdout, self.interface),
        )
