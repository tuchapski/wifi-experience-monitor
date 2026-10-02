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
  survey_active_ms?: number | null;
  survey_busy_ms?: number | null;
  survey_rx_ms?: number | null;
  survey_tx_ms?: number | null;
  survey_status?: string | null;
  survey_reason?: string | null;
  channel_utilization_percent?: number | null;
  channel_rx_percent?: number | null;
  channel_tx_percent?: number | null;
  scan_status?: string | null;
  scan_reason?: string | null;
  scan_running?: boolean | null;
  scan_last_completed_at?: string | null;
  scan_duration_ms?: number | null;
  scan_bss_count?: number | null;
  scan_associated_seen?: boolean | null;
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
  gateway_reachable?: boolean | null;
  gateway_latency_ms?: number | null;
  gateway_packet_loss_percent?: number | null;
  gateway_jitter_ms?: number | null;
  dns_success?: boolean | null;
  dns_latency_ms?: number | null;
  internet_reachable?: boolean | null;
  internet_latency_ms?: number | null;
  internet_packet_loss_percent?: number | null;
  internet_jitter_ms?: number | null;
  https_success?: boolean | null;
  https_status_code?: number | null;
  https_dns_ms?: number | null;
  https_tcp_connect_ms?: number | null;
  https_tls_handshake_ms?: number | null;
  https_ttfb_ms?: number | null;
  https_total_ms?: number | null;
  https_failure_elapsed_ms?: number | null;
}

export interface AgentCurrentState {
  agent_id: string;
  observed_at: string;
  updated_at: string;
  wifi: WifiCurrentState;
  network: NetworkCurrentState;
  collector_errors: string[];
  measurement_metadata?: Record<string, CurrentMeasurementMetadata>;
}

export interface CurrentMeasurementMetadata {
  observed_at: string;
  source: string;
  sample_count: number;
  unit: string | null;
  interval_seconds: number | null;
  labels: Record<string, string>;
  profile_version: string | null;
}

export type ClientExperienceStatus = "observed_ok" | "degraded" | "failure" | "partial"
  | "unavailable" | "stale" | "collection_error";

export interface ServiceObjectives {
  latency_ms: number | null;
  packet_loss_percent: number | null;
  jitter_ms: number | null;
  ttfb_ms: number | null;
}

export interface ExperienceProfile {
  automatic_capture: boolean;
  capture_pre_seconds: number;
  capture_post_seconds: number;
  capture_cooldown_seconds: number;
  enabled: boolean;
  name: string;
  location: string;
  dns_query: string;
  internet_target: string;
  https_url: string;
  interval_seconds: number;
  timeout_seconds: number;
  confirm_seconds: number;
  recover_seconds: number;
  minimum_samples: number;
  baseline_min_samples: number;
  baseline_min_seconds: number;
  local_network: ServiceObjectives;
  dns: ServiceObjectives;
  internet: ServiceObjectives;
  application: ServiceObjectives;
}

export interface ExperienceProfileResponse {
  agent_id: string;
  version: string | null;
  applied_version: string | null;
  profile: ExperienceProfile;
}

export type FindingStatus = "unknown" | "normal" | "candidate" | "active" | "recovering" | "recovered";
export interface DetectionFinding {
  rule_id: string;
  domain: string;
  metric: string;
  label: string;
  status: FindingStatus;
  previous_status: string | null;
  kind: "availability" | "objective" | "relative" | "none";
  reason: string;
  target: string | null;
  value: boolean | number | null;
  unit: string | null;
  objective: number | null;
  observed_at: string | null;
  since: string | null;
  observed_duration_seconds: number;
  consecutive_samples: number;
  evidence_gap: boolean;
  context: Record<string, string>;
  baseline: {
    status: "forming" | "ready" | "not_applicable";
    samples: number;
    median: number | null;
    mad: number | null;
    p95: number | null;
    upper_limit: number | null;
    established_at: string | null;
  };
}

export interface ClientDetection {
  agent_id: string;
  detector_version: string;
  evaluated_at: string;
  profile_version: string | null;
  applied_version: string | null;
  enabled: boolean;
  status: "disabled" | "pending_profile" | "unknown" | "observed_ok" | "candidate" | "active" | "recovering";
  active_count: number;
  findings: DetectionFinding[];
  limitations: string[];
}

export interface ExperienceMeasurement {
  metric: string;
  label: string;
  value: boolean | number | string | null;
  unit: string | null;
  quality: "current" | "legacy" | "stale" | "unavailable" | "invalid";
  observed_at: string | null;
  source: string | null;
  age_seconds: number | null;
  sample_count: number | null;
  interval_seconds: number | null;
  target: string | null;
  profile_version: string | null;
}

export interface ClientExperienceDomain {
  domain: string;
  label: string;
  status: ClientExperienceStatus;
  explanation: string;
  target: string | null;
  measurements: ExperienceMeasurement[];
}

export interface ClientExperience {
  agent_id: string;
  version: string;
  evaluated_at: string;
  state_observed_at: string | null;
  state_received_at: string | null;
  agent_online: boolean;
  max_measurement_age_seconds: number;
  status: ClientExperienceStatus;
  current_outcomes: number;
  total_outcomes: number;
  outcome_coverage_percent: number;
  domains: ClientExperienceDomain[];
  collector_errors: string[];
  limitations: string[];
}

export interface RfBssObservation {
  bssid: string;
  ssid: string | null;
  frequency_mhz: number;
  channel: number | null;
  band: "2.4ghz" | "5ghz" | "6ghz" | "unknown";
  rssi_dbm: number | null;
  associated: boolean;
  channel_width_mhz: number | null;
  beacon_interval_tu: number | null;
  capability: string | null;
  privacy: boolean;
  security: string[];
  phy_capabilities: string[];
  bss_load_station_count: number | null;
  bss_load_channel_utilization_raw: number | null;
  last_seen_ms: number | null;
}

export interface RfScanSnapshot {
  scan_id: string;
  sequence: number;
  observed_at: string;
  interface: string;
  duration_ms: number;
  received_at: string;
  bsses: RfBssObservation[];
}

export interface RfSampleStatistics {
  sample_count: number;
  minimum: number | null;
  average: number | null;
  maximum: number | null;
}

export interface RecordingRfScanWindow {
  scan_id: string;
  interface: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

export interface RecordingRfScanWindows {
  total_scans: number;
  loaded_scans: number;
  invalid_windows: number;
  truncated: boolean;
  windows: RecordingRfScanWindow[];
}

export interface RecordingRfSummary {
  scan_count: number;
  total_bss_observations: number;
  unique_bss: number;
  unique_ssids: number;
  first_scan_at: string | null;
  last_scan_at: string | null;
  maximum_scan_gap_seconds: number | null;
  scans_with_association: number;
  association_coverage_percent: number | null;
  visible_neighbors: RfSampleStatistics;
  same_channel_neighbors: RfSampleStatistics;
  same_ssid_neighbors: RfSampleStatistics;
  strong_neighbors: RfSampleStatistics;
  strong_neighbor_threshold_dbm: number;
  best_same_ssid_delta_db: RfSampleStatistics;
  stronger_same_ssid_scan_count: number;
  stronger_same_ssid_percent: number | null;
  association_transition_pairs: number;
  associated_bssid_changes: number;
  associated_frequency_changes: number;
  neighborhood_transition_pairs: number;
  neighborhood_changed_pairs: number;
  visible_bss_additions: number;
  visible_bss_removals: number;
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

export type DiagnosticEvidenceDomain =
  | "wifi_rf"
  | "local_network"
  | "dns"
  | "internet"
  | "application";

export type DiagnosticEvidenceDomainStatus =
  | "degraded"
  | "no_significant_change"
  | "unavailable";

export interface DiagnosticEvidenceDomainSummary {
  domain: DiagnosticEvidenceDomain;
  status: DiagnosticEvidenceDomainStatus;
  evaluated_metrics: string[];
  finding_metrics: string[];
}

export type DiagnosticProbableDomainStatus =
  | "probable"
  | "ambiguous"
  | "insufficient_evidence"
  | "not_observed";

export interface DiagnosticProbableDomainAssessment {
  method: "earliest-supported-domain-v1";
  status: DiagnosticProbableDomainStatus;
  domain: DiagnosticEvidenceDomain | null;
  degraded_domains: DiagnosticEvidenceDomain[];
  unresolved_domains: DiagnosticEvidenceDomain[];
  rationale: string;
}

export interface DiagnosticFinding {
  metric: string;
  evidence_domain: DiagnosticEvidenceDomain;
  direction: string;
  baseline: number;
  during: number;
  delta: number;
  after: number | null;
  recovery: string;
}

export interface DiagnosticWindowComparison {
  window_start: string;
  window_end: string;
  context_seconds: number;
  before_start: string;
  after_end: string;
  metrics: DiagnosticMetricComparison[];
  findings: DiagnosticFinding[];
  evidence_domains: DiagnosticEvidenceDomainSummary[];
}

export interface CorrelatedRecordingEvent {
  observed_at: string;
  event_type: string;
  severity: string;
  phase: "before" | "during" | "after";
  distance_seconds: number;
  seconds_from_window_start: number;
  data: Record<string, unknown>;
}

export interface DiagnosticEvidenceCorrelation {
  window_start: string;
  window_end: string;
  context_seconds: number;
  findings: DiagnosticFinding[];
  evidence_domains: DiagnosticEvidenceDomainSummary[];
  probable_domain: DiagnosticProbableDomainAssessment | null;
  events: CorrelatedRecordingEvent[];
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

export interface CrossLayerDiagnosticEpisode {
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  trigger_domain: DiagnosticEvidenceDomain;
  trigger_metric: string;
  observed_domains: DiagnosticEvidenceDomain[];
  scope: "single_domain" | "cross_layer";
  metrics: string[];
  degraded_samples: number;
  recovery_confirmed: boolean;
  domain_evidence: Partial<Record<DiagnosticEvidenceDomain, string[]>>;
  peak_deltas: Record<string, number>;
  baselines: Record<string, number>;
}

export type DiagnosticInvestigationFocus =
  | {
    source: "wifi_window";
    started_at: string;
    ended_at: string;
    duration_seconds: number;
    window: AnalysisDegradedWindow;
  }
  | {
    source: "cross_layer_episode";
    started_at: string;
    ended_at: string;
    duration_seconds: number;
    episode: CrossLayerDiagnosticEpisode;
  };

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
  cross_layer_episodes?: CrossLayerDiagnosticEpisode[];
  cross_layer_episode_summary?: {
    total: number;
    single_domain: number;
    cross_layer: number;
    baseline_metrics: number;
    unavailable_baseline_metrics: string[];
  };
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


export interface ClientEpisode {
  id: string; agent_id: string; domain: string; target: string | null;
  profile_version: string; detector_version: string; status: string; stored_status: string;
  started_at: string; confirmed_at: string; last_observed_at: string;
  recovered_at: string | null; closed_at: string | null; acknowledged_at: string | null;
  recurrence_count: number; observed_duration_seconds: number; evidence_gap: boolean;
  reason: string; context: Record<string, string>; opening_findings: DetectionFinding[]; findings: DetectionFinding[];
  capture: { recording_id: string | null; mode: string; status: string; requested_start: string;
    requested_end: string; coverage: Record<string, unknown> } | null;
  transitions: { kind: string; observed_at: string; data: Record<string, unknown> }[];
  transitions_truncated: boolean;
}
export interface ClientEpisodePage {
  agent_id: string; evaluated_at: string; total: number; offset: number; limit: number;
  episodes: ClientEpisode[];
}
