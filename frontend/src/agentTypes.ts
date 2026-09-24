export interface AgentCapability {
  capability: string;
  enabled: boolean;
  metadata: Record<string, unknown>;
}

export interface AgentSummary {
  id: string;
  name: string;
  hostname: string;
  agent_type: string;
  status: string;
  os_name: string | null;
  os_version: string | null;
  agent_version: string;
  first_seen_at: string;
  last_seen_at: string;
  capabilities: AgentCapability[];
}

export interface WifiCurrentState {
  connected?: boolean | null;
  interface?: string | null;
  ssid?: string | null;
  bssid?: string | null;
  frequency_mhz?: number | null;
  channel?: number | null;
  channel_width_mhz?: number | null;
  rssi_dbm?: number | null;
  signal_avg_dbm?: number | null;
  noise_dbm?: number | null;
  snr_db?: number | null;
  tx_rate_mbps?: number | null;
  rx_rate_mbps?: number | null;
  tx_mcs?: number | null;
  rx_mcs?: number | null;
  tx_nss?: number | null;
  rx_nss?: number | null;
  tx_phy?: string | null;
  rx_phy?: string | null;
  tx_packets?: number | null;
  tx_retries?: number | null;
  tx_failed?: number | null;
  rx_packets?: number | null;
  rx_drop_misc?: number | null;
}

export interface NetworkCurrentState {
  ipv4_address?: string | null;
  prefix_length?: number | null;
  gateway?: string | null;
  gateway_latency_ms?: number | null;
  dns_latency_ms?: number | null;
  internet_latency_ms?: number | null;
}

export interface AgentCurrentState {
  agent_id: string;
  observed_at: string;
  updated_at: string;
  wifi: WifiCurrentState;
  network: NetworkCurrentState;
  collector_errors: string[];
}

export interface TelemetryPoint {
  observed_at: string;
  metric: string;
  value: number;
  min_value: number | null;
  max_value: number | null;
  sample_count: number;
  unit: string | null;
  labels: Record<string, unknown>;
  received_at: string;
}

export interface AgentWithState {
  agent: AgentSummary;
  state: AgentCurrentState | null;
}

export interface DiagnosticRecording {
  id: string;
  agent_id: string;
  name: string;
  description: string | null;
  status: string;
  sync_status: string;
  profile_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  agent_version: string | null;
  schema_version: number;
  metrics_count: number;
  events_count: number;
  tests_count: number;
  artifacts_count: number;
  created_at: string;
  updated_at: string;
}

export interface StartRecordingInput {
  name: string;
  description: string | null;
  profile_id: string;
}

export interface RecordingMetricPoint {
  observed_at: string;
  metric: string;
  value: number;
  unit: string | null;
  labels: Record<string, unknown>;
  received_at: string;
}

export interface RecordingEvent {
  observed_at: string;
  event_type: string;
  severity: string;
  data: Record<string, unknown>;
  received_at: string;
}

export interface AnalysisMetricStats {
  samples: number;
  min: number;
  average: number;
  max: number;
  p10: number;
  p50: number;
  p90: number;
}

export interface AnalysisSignalWindow {
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  sample_count: number;
  minimum_dbm: number;
  average_dbm: number;
  threshold_dbm: number;
}

export interface RecordingAnalysisSummary {
  status: "critical" | "warning" | "observed" | "clear" | "limited";
  evidence_status: "complete" | "partial";
  evidence_groups: {
    signal: boolean;
    link_rate: boolean;
    state: boolean;
    counter_quality?: boolean;
    rf_utilization?: boolean;
  };
  finding_counts: {
    critical: number;
    warning: number;
    info: number;
  };
  rssi: AnalysisMetricStats | null;
  tx_rate_mbps: AnalysisMetricStats | null;
  rx_rate_mbps: AnalysisMetricStats | null;
  tx_retries_per_100_packets?: AnalysisMetricStats | null;
  tx_failed_percent?: AnalysisMetricStats | null;
  counter_intervals?: number;
  channel_utilization_percent?: AnalysisMetricStats | null;
  channel_rx_percent?: AnalysisMetricStats | null;
  channel_tx_percent?: AnalysisMetricStats | null;
  survey_intervals?: number;
  low_signal_windows: AnalysisSignalWindow[];
  very_low_signal_windows: AnalysisSignalWindow[];
  state_changes: {
    total: number;
    bssid: number;
    channel: number;
    disconnects: number;
  };
  limitations: string[];
}

export interface RecordingAnalysisFinding {
  code: string;
  severity: "critical" | "warning" | "info";
  title: string;
  message: string;
  next_action: string;
  evidence: Record<string, unknown>;
}

export interface RecordingAnalysis {
  id: string;
  recording_id: string;
  engine_version: string;
  status: string;
  source_metrics_count: number;
  source_events_count: number;
  summary: RecordingAnalysisSummary;
  findings: RecordingAnalysisFinding[];
  policy: Record<string, unknown>;
  created_at: string;
}
