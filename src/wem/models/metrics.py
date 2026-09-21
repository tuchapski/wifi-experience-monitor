from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class WifiMetrics:
    interface: str

    ssid: str | None = None
    bssid: str | None = None

    authorized: bool | None = None
    authenticated: bool | None = None
    associated: bool | None = None

    connected_time_seconds: int | None = None
    inactive_time_ms: int | None = None

    frequency_mhz: int | None = None
    channel: int | None = None
    channel_width_mhz: int | None = None

    signal_dbm: int | None = None
    signal_avg_dbm: int | None = None
    beacon_signal_avg_dbm: int | None = None

    tx_power_dbm: float | None = None

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

    tx_bytes: int | None = None
    tx_packets: int | None = None
    tx_retries: int | None = None
    tx_failed: int | None = None

    rx_bytes: int | None = None
    rx_packets: int | None = None
    rx_drop_misc: int | None = None

    beacon_rx: int | None = None
    beacon_loss: int | None = None
    beacon_interval_ms: int | None = None
    dtim_period: int | None = None

    wmm_enabled: bool | None = None
    mfp_enabled: bool | None = None

    power_save: bool | None = None


@dataclass(slots=True)
class NetworkMetrics:
    interface: str

    ipv4_address: str | None = None
    prefix_length: int | None = None

    gateway: str | None = None

    dns_servers: list[str] = field(default_factory=list)

    default_route_present: bool = False


@dataclass(slots=True)
class WifiDeltaMetrics:
    interval_seconds: float | None = None

    tx_packets_delta: int | None = None
    tx_retries_delta: int | None = None
    tx_failed_delta: int | None = None

    rx_packets_delta: int | None = None
    rx_drop_misc_delta: int | None = None

    tx_retries_per_100_packets: float | None = None
    tx_failed_percent: float | None = None
    rx_drop_percent: float | None = None

    association_changed: bool = False
    counter_reset_detected: bool = False


@dataclass(slots=True)
class ConnectivityMetrics:
    gateway_reachable: bool | None = None

    gateway_packet_loss_percent: float | None = None

    gateway_latency_min_ms: float | None = None
    gateway_latency_avg_ms: float | None = None
    gateway_latency_max_ms: float | None = None

    gateway_jitter_ms: float | None = None

    dns_success: bool | None = None
    dns_latency_ms: float | None = None
    dns_query: str | None = None
    dns_result: str | None = None

    internet_reachable: bool | None = None

    internet_packet_loss_percent: float | None = None

    internet_latency_min_ms: float | None = None
    internet_latency_avg_ms: float | None = None
    internet_latency_max_ms: float | None = None

    internet_jitter_ms: float | None = None

    https_success: bool | None = None
    https_status_code: int | None = None
    https_total_time_ms: float | None = None


@dataclass(slots=True)
class SensorHealthMetrics:
    interface: str

    interface_exists: bool = False
    interface_up: bool | None = None

    wireless_interface: bool | None = None

    driver: str | None = None
    firmware_version: str | None = None

    kernel_version: str | None = None

    rfkill_soft_blocked: bool | None = None
    rfkill_hard_blocked: bool | None = None

    network_manager_state: str | None = None
    network_manager_managed: bool | None = None

    power_save: bool | None = None


@dataclass(slots=True)
class CalibrationFinding:
    severity: str
    code: str
    message: str


@dataclass(slots=True)
class CalibrationResult:
    status: str

    calibrated: bool

    findings: list[CalibrationFinding] = field(default_factory=list)


@dataclass(slots=True)
class DiagnosticFinding:
    severity: str
    domain: str
    code: str
    message: str


@dataclass(slots=True)
class DiagnosticResult:
    overall_status: str
    probable_domain: str | None

    findings: list[DiagnosticFinding] = field(default_factory=list)


@dataclass(slots=True)
class Incident:
    code: str
    domain: str
    severity: str
    message: str

    first_seen_at: str
    opened_at: str | None

    consecutive_occurrences: int


@dataclass(slots=True)
class IncidentEvent:
    action: str

    code: str
    domain: str
    severity: str
    message: str

    first_seen_at: str
    opened_at: str | None
    resolved_at: str | None


@dataclass(slots=True)
class IncidentEvaluation:
    active_incidents: list[Incident] = field(default_factory=list)

    events: list[IncidentEvent] = field(default_factory=list)


@dataclass(slots=True)
class SensorSnapshot:
    timestamp: str

    health: SensorHealthMetrics
    calibration: CalibrationResult

    wifi: WifiMetrics
    wifi_delta: WifiDeltaMetrics | None

    network: NetworkMetrics
    connectivity: ConnectivityMetrics

    diagnostic: DiagnosticResult | None
    incidents: IncidentEvaluation | None

    collector_errors: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        health: SensorHealthMetrics,
        calibration: CalibrationResult,
        wifi: WifiMetrics,
        network: NetworkMetrics,
        connectivity: ConnectivityMetrics,
        wifi_delta: WifiDeltaMetrics | None = None,
        diagnostic: DiagnosticResult | None = None,
        incidents: IncidentEvaluation | None = None,
        errors: list[str] | None = None,
    ) -> "SensorSnapshot":
        return cls(
            timestamp=datetime.now(UTC).isoformat(),
            health=health,
            calibration=calibration,
            wifi=wifi,
            wifi_delta=wifi_delta,
            network=network,
            connectivity=connectivity,
            diagnostic=diagnostic,
            incidents=incidents,
            collector_errors=errors or [],
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return asdict(self)
