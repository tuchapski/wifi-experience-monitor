from dataclasses import dataclass
from datetime import datetime
from typing import Literal

WifiBand = Literal["2.4ghz", "5ghz", "6ghz", "unknown"]


@dataclass(frozen=True, slots=True)
class BssObservation:
    """One BSS observed by a Linux nl80211/iw scan."""

    bssid: str
    interface: str
    ssid: str | None
    frequency_mhz: int
    channel: int | None
    band: WifiBand
    rssi_dbm: float | None
    associated: bool = False
    channel_width_mhz: int | None = None
    beacon_interval_tu: int | None = None
    capability: str | None = None
    privacy: bool = False
    security: tuple[str, ...] = ()
    phy_capabilities: tuple[str, ...] = ()
    bss_load_station_count: int | None = None
    bss_load_channel_utilization_raw: int | None = None
    last_seen_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.interface.strip():
            raise ValueError("interface must not be empty")
        if self.frequency_mhz <= 0:
            raise ValueError("frequency_mhz must be positive")
        if self.channel is not None and self.channel <= 0:
            raise ValueError("channel must be positive when available")
        if self.bss_load_channel_utilization_raw is not None and not (
            0 <= self.bss_load_channel_utilization_raw <= 255
        ):
            raise ValueError("BSS Load channel utilization must be between 0 and 255")

    @property
    def bss_load_channel_utilization_percent(self) -> float | None:
        """Return AP-advertised BSS Load utilization, not local radio survey utilization."""

        if self.bss_load_channel_utilization_raw is None:
            return None
        return self.bss_load_channel_utilization_raw / 255 * 100


@dataclass(frozen=True, slots=True)
class RfScanResult:
    """Result of one RF neighborhood scan attempt."""

    interface: str
    observed_at: datetime
    duration_ms: float
    bsses: tuple[BssObservation, ...] = ()
    error: str | None = None
    recording_id: str | None = None

    def __post_init__(self) -> None:
        if not self.interface.strip():
            raise ValueError("interface must not be empty")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        if self.recording_id is not None and not self.recording_id.strip():
            raise ValueError("recording_id must not be blank when provided")

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def associated_bss(self) -> BssObservation | None:
        return next((bss for bss in self.bsses if bss.associated), None)
