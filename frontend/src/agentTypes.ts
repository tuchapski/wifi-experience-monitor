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
