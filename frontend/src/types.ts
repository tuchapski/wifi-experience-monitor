export interface WirelessInterface {
  name: string;

  phy: string | null;

  mac_address: string | null;

  interface_type: string | null;
}


export interface SensorConfiguration {
  interface: string | null;

  interval_seconds: number;
}


export interface SensorStatus {
  started_at: string | null;
  running: boolean;

  interface: string | null;

  interval_seconds: number;

  last_error: string | null;
}


export interface WifiMetrics {
  interface: string;

  ssid: string | null;
  bssid: string | null;

  authorized: boolean | null;
  authenticated: boolean | null;
  associated: boolean | null;

  connected_time_seconds: number | null;
  inactive_time_ms: number | null;

  frequency_mhz: number | null;
  channel: number | null;
  channel_width_mhz: number | null;

  signal_dbm: number | null;
  signal_avg_dbm: number | null;
  beacon_signal_avg_dbm: number | null;

  tx_power_dbm: number | null;

  tx_bitrate_mbps: number | null;
  rx_bitrate_mbps: number | null;

  tx_channel_width_mhz?: number | null;
  rx_channel_width_mhz?: number | null;

  tx_mcs: number | null;
  rx_mcs: number | null;

  tx_nss: number | null;
  rx_nss: number | null;

  tx_phy_mode: string | null;
  rx_phy_mode: string | null;

  tx_short_gi: boolean | null;
  rx_short_gi: boolean | null;

  tx_bytes: number | null;
  tx_packets: number | null;
  tx_retries: number | null;
  tx_failed: number | null;

  rx_bytes: number | null;
  rx_packets: number | null;
  rx_drop_misc: number | null;

  beacon_rx: number | null;
  beacon_loss: number | null;
  beacon_interval_ms: number | null;
  dtim_period: number | null;

  wmm_enabled: boolean | null;
  mfp_enabled: boolean | null;

  power_save: boolean | null;
}


export interface WifiDeltaMetrics {
  unavailable_reason?: string | null;
  interval_seconds: number | null;

  tx_packets_delta: number | null;
  tx_retries_delta: number | null;
  tx_failed_delta: number | null;

  rx_packets_delta: number | null;
  rx_drop_misc_delta: number | null;

  tx_retries_per_100_packets: number | null;
  tx_failed_percent: number | null;
  rx_drop_percent: number | null;

  association_changed: boolean;
  counter_reset_detected: boolean;
}


export interface NetworkMetrics {
  interface: string;

  ipv4_address: string | null;
  prefix_length: number | null;

  gateway: string | null;

  dns_servers: string[];

  default_route_present: boolean;
}


export interface TestOutcome {
  status: "passed" | "failed" | "error" | "skipped" | "unavailable" | "observed";
  reason: string;
  scope: string;
}

export interface ConnectivityMetrics {
  tests?: Record<string, TestOutcome>;

  gateway_reachable: boolean | null;

  gateway_packet_loss_percent: number | null;

  gateway_latency_min_ms: number | null;
  gateway_latency_avg_ms: number | null;
  gateway_latency_max_ms: number | null;
  gateway_jitter_ms: number | null;

  dns_success: boolean | null;
  dns_latency_ms: number | null;
  dns_query: string | null;
  dns_result: string | null;

  internet_reachable: boolean | null;

  internet_packet_loss_percent: number | null;

  internet_latency_min_ms: number | null;
  internet_latency_avg_ms: number | null;
  internet_latency_max_ms: number | null;
  internet_jitter_ms: number | null;

  https_success: boolean | null;
  https_status_code: number | null;
  https_total_time_ms: number | null;
}


export interface SensorHealthMetrics {
  interface: string;

  interface_exists: boolean | null;

  interface_up: boolean | null;

  wireless_interface: boolean | null;

  driver: string | null;

  firmware_version: string | null;

  kernel_version: string | null;

  rfkill_soft_blocked: boolean | null;

  rfkill_hard_blocked: boolean | null;

  network_manager_state: string | null;

  network_manager_managed: boolean | null;

  power_save: boolean | null;
}


export interface CalibrationFinding {
  severity: string;

  code: string;

  message: string;
}


export interface CalibrationResult {
  checks?: Record<string, TestOutcome>;
  status: string;

  calibrated: boolean;

  findings: CalibrationFinding[];
}


export interface DiagnosticFinding {
  severity: string;

  domain: string;

  code: string;

  message: string;
}


export interface DiagnosticResult {
  complete?: boolean;
  overall_status: string;

  probable_domain: string | null;

  findings: DiagnosticFinding[];
}

export interface Recommendation {
  code: string;
  severity: string;
  title: string;
  action: string;
  rationale: string;
  evidence: string;
}


export interface Incident {
  code: string;

  domain: string;

  severity: string;

  message: string;

  first_seen_at: string;

  opened_at: string | null;

  consecutive_occurrences: number;
}


export interface IncidentEvent {
  action: string;

  code: string;

  domain: string;

  severity: string;

  message: string;

  first_seen_at: string;

  opened_at: string | null;

  resolved_at: string | null;
}


export interface IncidentEvaluation {
  active_incidents: Incident[];

  events: IncidentEvent[];
}


export interface SensorSnapshot {
  timestamp: string;

  health: SensorHealthMetrics;

  calibration: CalibrationResult;

  wifi: WifiMetrics;

  wifi_delta: WifiDeltaMetrics | null;

  network: NetworkMetrics;

  connectivity: ConnectivityMetrics;

  diagnostic: DiagnosticResult | null;

  incidents: IncidentEvaluation | null;

  collector_errors: string[];

  recommendations?: Recommendation[];
}


export interface HistoryRecord {
  id: number;

  timestamp: string;

  interface: string;

  ssid: string | null;

  bssid: string | null;

  signal_dbm: number | null;

  signal_avg_dbm: number | null;

  gateway_latency_avg_ms: number | null;

  gateway_packet_loss_percent: number | null;

  internet_latency_avg_ms: number | null;

  internet_packet_loss_percent: number | null;

  dns_latency_ms: number | null;

  https_total_time_ms: number | null;

  tx_retries_per_100_packets: number | null;

  overall_status: string | null;

  probable_domain: string | null;
}


export interface IncidentRecord {
  id: number;

  code: string;

  domain: string;

  severity: string;

  message: string;

  status: string;

  first_seen_at: string;

  opened_at: string;

  resolved_at: string | null;

  duration_seconds: number | null;
}


export interface HistoryAggregate {
  avg: number | null;
  min: number | null;
  max: number | null;
  count: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
}

export interface HistoryPoint {
  timestamp: string;
  sample_count: number;
  metrics: Record<string, HistoryAggregate>;
}

export interface HistoryWindow {
  interface: string;
  start: string;
  end: string;
  bucket_seconds: number;
  total_samples: number;
  points: HistoryPoint[];
  events: EnvironmentChange[];
}

export interface EnvironmentChange {
  code: string;
  field: string;
  previous: string | number | boolean;
  current: string | number | boolean;
  message: string;
  severity: string;
  timestamp?: string;
}
