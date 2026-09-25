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
  tx_retries_per_100_packets?: number | null;
  tx_failed_percent?: number | null;
  link_score?: LinkScore | null;
}

export interface LinkScoreComponent {
  metric: string;
  label: string;
  unit: string;
  weight_percent: number;
  reading: number | null;
  score: number | null;
}

export interface LinkScore {
  version: string;
  value: number | null;
  status: "measured" | "provisional" | "disconnected" | "unavailable";
  coverage_percent: number;
  components: LinkScoreComponent[];
  limitations: string[];
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

export interface CreateDiagnosticProjectInput {
  name: string;
  objective: string | null;
  site: string | null;
  location: string | null;
  profile_id: string;
  max_duration_minutes: number;
  agent_ids: string[];
  agent_locations: Record<string, string>;
}

export interface ProjectAnalysisSummary {
  engine_version: string;
  assessment: string;
  evidence_status: string;
  findings_count: number;
  top_findings: { code: string; severity: string; title: string }[];
}

export interface DiagnosticProjectRecording {
  agent_id: string;
  recording_id: string | null;
  location: string | null;
  status: string | null;
  sync_status: string | null;
  analysis: ProjectAnalysisSummary | null;
}

export interface DiagnosticProjectRun {
  id: string;
  project_id: string;
  started_at: string;
  recordings: DiagnosticProjectRecording[];
}

export interface DiagnosticProject {
  id: string;
  name: string;
  objective: string | null;
  site: string | null;
  location: string | null;
  profile_id: string;
  max_duration_minutes: number;
  agent_ids: string[];
  agent_locations: Record<string, string | null>;
  created_at: string;
  runs: DiagnosticProjectRun[];
}

export interface DiagnosticRecording {
  id: string;
  agent_id: string;
  project_id: string | null;
  project_name: string | null;
  project_run_id: string | null;
  name: string;
  description: string | null;
  site: string | null;
  location: string | null;
  status: string;
  sync_status: string;
  profile_id: string | null;
  max_duration_minutes: number | null;
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

export interface RecordingMetricOverview {
  metric: string;
  sample_count: number;
  minimum: number | null;
  average: number | null;
  maximum: number | null;
  points: { observed_at: string; value: number }[];
}

export interface DiagnosticMetricStatistics {
  sample_count: number;
  minimum: number | null;
  average: number | null;
  maximum: number | null;
}

export interface DiagnosticMetricComparison {
  metric: string;
  before: DiagnosticMetricStatistics;
  during: DiagnosticMetricStatistics;
  after: DiagnosticMetricStatistics;
}

export interface DiagnosticWindowComparison {
  window_start: string;
  window_end: string;
  context_seconds: number;
  before_start: string;
  after_end: string;
  metrics: DiagnosticMetricComparison[];
}

export interface StartRecordingInput {
  name: string;
  description: string | null;
  site: string | null;
  location: string | null;
  profile_id: string;
  max_duration_minutes: number;
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

export interface AnalysisDegradedWindow {
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  sample_count: number;
  severity: "critical" | "warning";
  domains: string[];
  evidence: string[];
  minimum_rssi_dbm: number | null;
  maximum_retries_per_100_packets: number | null;
  maximum_tx_failed_percent: number | null;
  maximum_channel_utilization_percent: number | null;
}

export interface BssidMetricComparison {
  before_samples: number;
  after_samples: number;
  before_median: number | null;
  after_median: number | null;
  delta: number | null;
}

export interface BssidTransitionComparison {
  observed_at: string;
  previous_bssid: string;
  current_bssid: string;
  comparison_seconds: number;
  status: "comparable" | "limited";
  limitations: string[];
  metrics: Record<string, BssidMetricComparison>;
}

export interface CollectionIntegrity {
  status: "continuous" | "interrupted" | "impaired" | "unavailable";
  cycle_count: number;
  configured_interval_seconds: number | null;
  gap_threshold_seconds: number | null;
  collector_error_cycles: number;
  gaps: Array<{
    started_at: string;
    ended_at: string;
    duration_seconds: number;
  }>;
}

export interface DisconnectionInterval {
  disconnected_at: string;
  reconnected_at: string | null;
  status: "bounded" | "limited" | "open";
  duration_seconds: number | null;
  limitations: string[];
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
    temporal_correlation?: boolean;
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
  degraded_windows?: AnalysisDegradedWindow[];
  bssid_transitions?: BssidTransitionComparison[];
  collection_integrity?: CollectionIntegrity;
  disconnection_intervals?: DisconnectionInterval[];
  disconnection_summary?: {
    total: number;
    bounded: number;
    limited: number;
    open: number;
  };
  temporal_correlation?: {
    evaluable_samples: number;
    correlated_samples: number;
    window_count: number;
  };
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
