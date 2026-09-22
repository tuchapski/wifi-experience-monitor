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

  session_id: number | null;
  profile_id: number;
  profile_version_id: number;
  profile_name: string;
  profile_version: number;
}


export interface SyntheticTestConfiguration {
  enabled: boolean;
  interval_seconds: number;
  timeout_seconds: number | null;
}

export interface ServiceSloTargetConfiguration {
  availability_warning_percent: number;
  availability_critical_percent: number;
  latency_p95_warning_ms: number;
  latency_p95_critical_ms: number;
  packet_loss_p95_warning_percent: number | null;
  packet_loss_p95_critical_percent: number | null;
}

export interface TestProfileConfiguration {
  schema_version: 1;
  sampling: {
    wifi_interval_seconds: number;
  };
  tests: {
    gateway: SyntheticTestConfiguration & {
      automatic_gateway: boolean;
      target: string | null;
    };
    dns: SyntheticTestConfiguration & {
      query: string;
    };
    internet: SyntheticTestConfiguration & {
      target: string;
    };
    https: SyntheticTestConfiguration & {
      url: string;
    };
  };
  thresholds: {
    wifi: {
      rssi_warning_dbm: number;
      rssi_critical_dbm: number;
      retry_warning_percent: number;
      retry_critical_percent: number;
      tx_failure_critical_percent: number;
    };
    gateway: {
      latency_warning_ms: number;
      packet_loss_warning_percent: number;
      packet_loss_critical_percent: number;
    };
    dns: {
      latency_warning_ms: number;
    };
    internet: {
      latency_warning_ms: number;
      packet_loss_warning_percent: number;
      packet_loss_critical_percent: number;
    };
    https: {
      response_warning_ms: number;
    };
    connection_cycle: {
      window_size: number;
      minimum_samples: number;
      p95_warning_ms: number;
      p95_critical_ms: number;
    };
    adaptive_baseline: {
      enabled: boolean;
      lookback_hours: number;
      minimum_samples: number;
      max_samples: number;
      warning_sigma: number;
      critical_sigma: number;
    };
    service_slo: {
      enabled: boolean;
      window_size: number;
      minimum_samples: number;
      gateway: ServiceSloTargetConfiguration;
      internet: ServiceSloTargetConfiguration;
      dns: ServiceSloTargetConfiguration;
      https: ServiceSloTargetConfiguration;
    };
  };
}

export interface TestProfileSummary {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  active: boolean;
  version: number;
  version_id: number;
  created_at: string;
  updated_at: string;
  version_created_at: string;
}

export interface TestProfile extends TestProfileSummary {
  configuration: TestProfileConfiguration;
}

export interface TestProfileVersion {
  id: number;
  profile_id: number;
  version: number;
  active: boolean;
  created_at: string;
  configuration: TestProfileConfiguration;
}

export interface TestProfileWrite {
  name: string;
  description: string | null;
  enabled: boolean;
  configuration: TestProfileConfiguration;
}


export interface WifiSurveyMetrics {
  status: "available" | "partial" | "unavailable" | "unsupported" | "error";
  reason: string;
  frequency_mhz: number | null;
  noise_dbm: number | null;
  snr_db: number | null;
  active_ms: number | null;
  busy_ms: number | null;
  rx_ms: number | null;
  tx_ms: number | null;
}

export interface WifiMetrics {
  survey?: WifiSurveyMetrics;
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
  survey_unavailable_reason?: string | null;
  survey_active_ms_delta?: number | null;
  channel_utilization_percent?: number | null;
  channel_rx_percent?: number | null;
  channel_tx_percent?: number | null;
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
  status: "passed" | "failed" | "error" | "skipped" | "disabled" | "unavailable" | "observed";
  reason: string;
  scope: string;
  observed_at?: string | null;
  fresh?: boolean;
  age_seconds?: number | null;
}

export interface ConnectionStageMetric {
  status: "observed" | "pending" | "unavailable";
  observed_at: string | null;
  elapsed_ms: number | null;
  estimated: boolean;
  reason: string;
  source?: "sampling" | "networkmanager_dbus";
}

export interface ConnectionCycleMetrics {
  session_id: string;
  session_type: "observed_existing" | "initial_connect" | "reconnect" | "roam" | "network_change" | "reassociation";
  state: "connecting" | "ready" | "disconnected";
  ssid: string | null;
  bssid: string | null;
  started_at: string | null;
  last_observed_at: string;
  completed_at: string | null;
  total_time_ms: number | null;
  sample_resolution_ms: number | null;
  stages: Record<string, ConnectionStageMetric>;
  limitations: string[];
  timing_source?: "sampling" | "networkmanager_dbus+sampling";
  event_monitor_status?: "not_started" | "active" | "unavailable" | "error" | "stopped";
  event_monitor_reason?: string | null;
  networkmanager_state?: number | null;
  networkmanager_state_name?: string | null;
  networkmanager_event_count?: number;
}

export interface ConnectionCycleSloMetrics {
  status: "insufficient_data" | "healthy" | "warning" | "critical";
  sample_count: number;
  minimum_samples: number;
  window_size: number;
  p95_ms: number | null;
  warning_threshold_ms: number;
  critical_threshold_ms: number;
  latest_cycle_ms: number | null;
  fresh: boolean;
  reason: string;
}

export interface AdaptiveBaselineMetric {
  key: string;
  label: string;
  unit: string;
  status: "unavailable" | "insufficient_data" | "healthy" | "warning" | "critical";
  current: number | null;
  baseline_median: number | null;
  baseline_mad: number | null;
  robust_sigma: number | null;
  deviation_sigma: number | null;
  sample_count: number;
  minimum_samples: number;
  reason: string;
}

export interface AdaptiveBaselineMetrics {
  status: "disabled" | "insufficient_data" | "healthy" | "warning" | "critical";
  ssid: string | null;
  lookback_hours: number;
  minimum_samples: number;
  max_samples: number;
  warning_sigma: number;
  critical_sigma: number;
  metrics: AdaptiveBaselineMetric[];
  fresh: boolean;
  reason: string;
}

export interface ServiceSloMetric {
  service: string;
  status: "disabled" | "insufficient_data" | "healthy" | "warning" | "critical";
  attempt_count: number;
  measurable_count: number;
  success_count: number;
  failure_count: number;
  measurement_error_count: number;
  availability_percent: number | null;
  latency_sample_count: number;
  latency_p95_ms: number | null;
  packet_loss_sample_count: number;
  packet_loss_p95_percent: number | null;
  availability_warning_percent: number;
  availability_critical_percent: number;
  latency_p95_warning_ms: number;
  latency_p95_critical_ms: number;
  packet_loss_p95_warning_percent: number | null;
  packet_loss_p95_critical_percent: number | null;
  fresh: boolean;
  reason: string;
}

export interface ServiceSloMetrics {
  status: "disabled" | "insufficient_data" | "healthy" | "warning" | "critical";
  enabled: boolean;
  window_size: number;
  minimum_samples: number;
  services: Record<string, ServiceSloMetric>;
  fresh: boolean;
  reason: string;
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


export interface ScoreMetric {
  key: string;
  label: string;
  weight: number;
  unit: string;
  value: number | null;
  score: number | null;
  state: "measured" | "failed" | "unavailable";
  reason: string;
  rule: string;
}

export interface ScoreComponent {
  key: string;
  label: string;
  weight: number;
  coverage_percent: number;
  score: number | null;
  scope: string;
  metrics: ScoreMetric[];
  available_weight: number;
  effective_weight: number;
  contribution: number | null;
  deduction: number | null;
}

export interface ExperienceScore {
  policy_version: string;
  value: number | null;
  status: "complete" | "partial" | "unavailable";
  coverage_percent: number;
  minimum_coverage_percent: number;
  components: ScoreComponent[];
  reasons: string[];
}

export interface SensorSnapshot {
  experience_score?: ExperienceScore | null;
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
  connection_cycle?: ConnectionCycleMetrics | null;
  connection_cycle_slo?: ConnectionCycleSloMetrics | null;
  adaptive_baseline?: AdaptiveBaselineMetrics | null;
  service_slo?: ServiceSloMetrics | null;

  monitoring?: {
    session_id: number;
    profile: {
      profile_id: number;
      profile_version_id: number;
      name: string;
      version: number;
    };
  } | null;
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

  first_seen_at: string;

  started_at: string;

  ended_at: string | null;

  duration_seconds: number;

  is_open: boolean;
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

export interface ConnectionCycleAggregate extends HistoryAggregate {
  sources?: Record<string, number>;
}

export interface ConnectionCycleSummary {
  total_cycles: number;
  ready_cycles: number;
  measurable_cycles: number;
  unmeasured_cycles: number;
  by_type: Record<string, number>;
  by_state: Record<string, number>;
  by_timing_source: Record<string, number>;
  total_time_ms: ConnectionCycleAggregate;
  stages: Record<string, ConnectionCycleAggregate>;
}

export interface ServiceSloHistoryMetric {
  attempt_count: number;
  measurable_count: number;
  success_count: number;
  failure_count: number;
  measurement_error_count: number;
  availability_percent: number | null;
  latency_ms: HistoryAggregate;
  packet_loss_percent: HistoryAggregate;
}

export type ServiceSloHistorySummary = Record<string, ServiceSloHistoryMetric>;

export interface HistorySummary {
  sample_count: number;
  metrics: Record<string, HistoryAggregate>;
}

export interface HistoryComparison {
  current: HistorySummary;
  previous: HistorySummary;
  previous_start: string;
  previous_end: string;
  connection_cycles?: {
    current: ConnectionCycleSummary;
    previous: ConnectionCycleSummary;
  };
  service_slo?: {
    current: ServiceSloHistorySummary;
    previous: ServiceSloHistorySummary;
  };
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
  connection_cycles?: ConnectionCycleMetrics[];
  connection_cycle_summary?: ConnectionCycleSummary;
  service_slo_summary?: ServiceSloHistorySummary;
  summary?: HistorySummary;
  comparison?: HistoryComparison;
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
