from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class WifiSurveyMetrics:
    status: str = "unavailable"
    reason: str = "Survey measurements have not been collected."
    frequency_mhz: int | None = None
    noise_dbm: int | None = None
    snr_db: int | None = None
    active_ms: int | None = None
    busy_ms: int | None = None
    rx_ms: int | None = None
    tx_ms: int | None = None


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

    tx_channel_width_mhz: int | None = None
    rx_channel_width_mhz: int | None = None

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

    survey: WifiSurveyMetrics = field(default_factory=WifiSurveyMetrics)


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
    unavailable_reason: str | None = None
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

    survey_unavailable_reason: str | None = None
    survey_active_ms_delta: int | None = None
    channel_utilization_percent: float | None = None
    channel_rx_percent: float | None = None
    channel_tx_percent: float | None = None


@dataclass(slots=True)
class TestOutcome:
    status: str
    reason: str
    scope: str = "selected_interface"
    observed_at: str | None = None
    fresh: bool = True
    age_seconds: float | None = 0.0


@dataclass(slots=True)
class ConnectivityMetrics:
    tests: dict[str, TestOutcome] = field(default_factory=dict)

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
class ConnectionStageMetric:
    status: str
    observed_at: str | None = None
    elapsed_ms: float | None = None
    estimated: bool = False
    reason: str = ""
    source: str = "sampling"


@dataclass(slots=True)
class ConnectionCycleMetrics:
    session_id: str
    session_type: str
    state: str
    ssid: str | None
    bssid: str | None
    started_at: str | None
    last_observed_at: str
    completed_at: str | None
    total_time_ms: float | None
    sample_resolution_ms: float | None
    stages: dict[str, ConnectionStageMetric] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    timing_source: str = "sampling"
    event_monitor_status: str = "unavailable"
    event_monitor_reason: str | None = None
    networkmanager_state: int | None = None
    networkmanager_state_name: str | None = None
    networkmanager_event_count: int = 0


@dataclass(slots=True)
class ConnectionCycleSloMetrics:
    status: str
    sample_count: int
    minimum_samples: int
    window_size: int
    p95_ms: float | None
    warning_threshold_ms: float
    critical_threshold_ms: float
    latest_cycle_ms: float | None
    fresh: bool
    reason: str


@dataclass(slots=True)
class AdaptiveBaselineMetric:
    key: str
    label: str
    unit: str
    status: str
    current: float | None
    baseline_median: float | None
    baseline_mad: float | None
    robust_sigma: float | None
    deviation_sigma: float | None
    sample_count: int
    minimum_samples: int
    reason: str


@dataclass(slots=True)
class AdaptiveBaselineMetrics:
    status: str
    ssid: str | None
    lookback_hours: int
    minimum_samples: int
    max_samples: int
    warning_sigma: float
    critical_sigma: float
    metrics: list[AdaptiveBaselineMetric] = field(default_factory=list)
    fresh: bool = False
    reason: str = ""


@dataclass(slots=True)
class SensorHealthMetrics:
    interface: str

    interface_exists: bool | None = None
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

    checks: dict[str, TestOutcome] = field(default_factory=dict)

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
    complete: bool = True

    findings: list[DiagnosticFinding] = field(default_factory=list)


@dataclass(slots=True)
class Recommendation:
    code: str
    severity: str
    title: str
    action: str
    rationale: str
    evidence: str


@dataclass(slots=True)
class EnvironmentChange:
    """A change in the radio association or operating environment."""

    code: str
    field: str
    previous: str | int | float | bool
    current: str | int | float | bool
    message: str
    severity: str = "info"


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
class ScoreMetric:
    key: str
    label: str
    weight: float
    unit: str
    value: float | None
    score: float | None
    state: str
    reason: str
    rule: str


@dataclass(slots=True)
class ScoreComponent:
    key: str
    label: str
    weight: float
    coverage_percent: float
    score: float | None
    scope: str
    metrics: list[ScoreMetric]
    available_weight: float = 0.0
    effective_weight: float = 0.0
    contribution: float | None = None
    deduction: float | None = None


@dataclass(slots=True)
class ExperienceScore:
    policy_version: str
    value: float | None
    status: str
    coverage_percent: float
    minimum_coverage_percent: float
    components: list[ScoreComponent]
    reasons: list[str]


@dataclass(slots=True)
class ProfileReference:
    profile_id: int
    profile_version_id: int
    name: str
    version: int


@dataclass(slots=True)
class MonitoringContext:
    session_id: int
    profile: ProfileReference


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

    environment_changes: list[EnvironmentChange] = field(default_factory=list)

    recommendations: list[Recommendation] = field(default_factory=list)

    collector_errors: list[str] = field(default_factory=list)

    experience_score: ExperienceScore | None = None
    connection_cycle: ConnectionCycleMetrics | None = None
    connection_cycle_slo: ConnectionCycleSloMetrics | None = None
    adaptive_baseline: AdaptiveBaselineMetrics | None = None
    monitoring: MonitoringContext | None = None

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
        environment_changes: list[EnvironmentChange] | None = None,
        recommendations: list[Recommendation] | None = None,
        errors: list[str] | None = None,
        experience_score: ExperienceScore | None = None,
        monitoring: MonitoringContext | None = None,
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
            environment_changes=environment_changes or [],
            recommendations=recommendations or [],
            collector_errors=errors or [],
            experience_score=experience_score,
            monitoring=monitoring,
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return asdict(self)
