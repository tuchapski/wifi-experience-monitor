from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class WifiMetrics:
    interface: str

    # Association
    ssid: str | None = None
    bssid: str | None = None

    authorized: bool | None = None
    authenticated: bool | None = None
    associated: bool | None = None

    connected_time_seconds: int | None = None
    inactive_time_ms: int | None = None

    # RF
    frequency_mhz: int | None = None
    channel: int | None = None
    channel_width_mhz: int | None = None

    signal_dbm: int | None = None
    signal_avg_dbm: int | None = None
    beacon_signal_avg_dbm: int | None = None

    tx_power_dbm: float | None = None

    # PHY
    tx_bitrate_mbps: float | None = None
    rx_bitrate_mbps: float | None = None

    tx_mcs: int | None = None
    rx_mcs: int | None = None

    tx_nss: int | None = None
    rx_nss: int | None = None

    tx_phy_mode: str | None = None
    rx_phy_mode: str | None = None

    tx_short_gi: bool | None = None
    rx_short_gi: bool | None = None

    # Traffic
    tx_bytes: int | None = None
    tx_packets: int | None = None
    tx_retries: int | None = None
    tx_failed: int | None = None

    rx_bytes: int | None = None
    rx_packets: int | None = None
    rx_drop_misc: int | None = None

    # Beacon
    beacon_rx: int | None = None
    beacon_loss: int | None = None
    beacon_interval_ms: int | None = None
    dtim_period: int | None = None

    # WLAN features
    wmm_enabled: bool | None = None
    mfp_enabled: bool | None = None

    power_save: bool | None = None


@dataclass(slots=True)
class SensorSnapshot:
    timestamp: str
    wifi: WifiMetrics
    collector_errors: list[str]

    @classmethod
    def create(
        cls,
        wifi: WifiMetrics,
        errors: list[str] | None = None,
    ) -> "SensorSnapshot":
        return cls(
            timestamp=datetime.now(UTC).isoformat(),
            wifi=wifi,
            collector_errors=errors or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
