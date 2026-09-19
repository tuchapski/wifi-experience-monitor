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


export interface ConnectivityMetrics {
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


export interface DiagnosticFinding {
  severity: string;
  domain: string;
  code: string;
  message: string;
}


export interface DiagnosticResult {
  overall_status: string;
  probable_domain: string | null;

  findings: DiagnosticFinding[];
}


export interface SensorSnapshot {
  timestamp: string;

  wifi: WifiMetrics;

  wifi_delta: WifiDeltaMetrics | null;

  network: NetworkMetrics;

  connectivity: ConnectivityMetrics;

  diagnostic: DiagnosticResult | null;

  collector_errors: string[];
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
