"""Shared deterministic policy for diagnostic metric deterioration and evidence domains."""

from wifi_server.metric_names import (
    NETWORK_DNS_LATENCY_MS,
    NETWORK_GATEWAY_JITTER_MS,
    NETWORK_GATEWAY_LATENCY_MS,
    NETWORK_GATEWAY_PACKET_LOSS_PERCENT,
    NETWORK_HTTPS_TOTAL_MS,
    NETWORK_INTERNET_JITTER_MS,
    NETWORK_INTERNET_LATENCY_MS,
    NETWORK_INTERNET_PACKET_LOSS_PERCENT,
    WIFI_CHANNEL_RX_PERCENT,
    WIFI_CHANNEL_TX_PERCENT,
    WIFI_CHANNEL_UTILIZATION_PERCENT,
    WIFI_NOISE_DBM,
    WIFI_RSSI_DBM,
    WIFI_RX_RATE_MBPS,
    WIFI_SIGNAL_AVG_DBM,
    WIFI_SNR_DB,
    WIFI_TX_FAILED_PERCENT,
    WIFI_TX_RATE_MBPS,
    WIFI_TX_RETRIES_PER_100_PACKETS,
)

# Minimum change from baseline required before a metric is considered deteriorated.
# Direction indicates which movement represents deterioration for that metric.
FINDING_RULES: dict[str, tuple[float, str]] = {
    WIFI_RSSI_DBM: (5.0, "decrease"),
    WIFI_SIGNAL_AVG_DBM: (5.0, "decrease"),
    WIFI_SNR_DB: (5.0, "decrease"),
    WIFI_TX_RATE_MBPS: (20.0, "decrease"),
    WIFI_RX_RATE_MBPS: (20.0, "decrease"),
    WIFI_TX_RETRIES_PER_100_PACKETS: (5.0, "increase"),
    WIFI_TX_FAILED_PERCENT: (2.0, "increase"),
    WIFI_CHANNEL_UTILIZATION_PERCENT: (15.0, "increase"),
    WIFI_CHANNEL_RX_PERCENT: (15.0, "increase"),
    WIFI_CHANNEL_TX_PERCENT: (15.0, "increase"),
    WIFI_NOISE_DBM: (5.0, "increase"),
    NETWORK_GATEWAY_LATENCY_MS: (10.0, "increase"),
    NETWORK_GATEWAY_PACKET_LOSS_PERCENT: (1.0, "increase"),
    NETWORK_GATEWAY_JITTER_MS: (5.0, "increase"),
    NETWORK_DNS_LATENCY_MS: (50.0, "increase"),
    NETWORK_INTERNET_LATENCY_MS: (20.0, "increase"),
    NETWORK_INTERNET_PACKET_LOSS_PERCENT: (1.0, "increase"),
    NETWORK_INTERNET_JITTER_MS: (10.0, "increase"),
    NETWORK_HTTPS_TOTAL_MS: (100.0, "increase"),
}

EVIDENCE_DOMAIN_ORDER = (
    "wifi_rf",
    "local_network",
    "dns",
    "internet",
    "application",
)

EVIDENCE_DOMAIN_METRICS: dict[str, frozenset[str]] = {
    "wifi_rf": frozenset(
        {
            WIFI_RSSI_DBM,
            WIFI_SIGNAL_AVG_DBM,
            WIFI_SNR_DB,
            WIFI_TX_RATE_MBPS,
            WIFI_RX_RATE_MBPS,
            WIFI_TX_RETRIES_PER_100_PACKETS,
            WIFI_TX_FAILED_PERCENT,
            WIFI_CHANNEL_UTILIZATION_PERCENT,
            WIFI_CHANNEL_RX_PERCENT,
            WIFI_CHANNEL_TX_PERCENT,
            WIFI_NOISE_DBM,
        }
    ),
    "local_network": frozenset(
        {
            NETWORK_GATEWAY_LATENCY_MS,
            NETWORK_GATEWAY_PACKET_LOSS_PERCENT,
            NETWORK_GATEWAY_JITTER_MS,
        }
    ),
    "dns": frozenset({NETWORK_DNS_LATENCY_MS}),
    "internet": frozenset(
        {
            NETWORK_INTERNET_LATENCY_MS,
            NETWORK_INTERNET_PACKET_LOSS_PERCENT,
            NETWORK_INTERNET_JITTER_MS,
        }
    ),
    "application": frozenset({NETWORK_HTTPS_TOTAL_MS}),
}

METRIC_EVIDENCE_DOMAIN: dict[str, str] = {
    metric: domain for domain, metrics in EVIDENCE_DOMAIN_METRICS.items() for metric in metrics
}
