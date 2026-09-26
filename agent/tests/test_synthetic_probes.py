from unittest.mock import patch

from wifi_agent.collectors.command import CommandResult
from wifi_agent.collectors.connectivity import probe_dns, probe_https, probe_ping
from wifi_agent.processors import TelemetryAggregator


def _values(result):
    return {item.metric: item.value for item in result.observations}


@patch("wifi_agent.collectors.connectivity.run_command")
def test_ping_probe_emits_loss_latency_jitter_and_reachability(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout=(
            "4 packets transmitted, 4 received, 0% packet loss, time 601ms\n"
            "rtt min/avg/max/mdev = 1.100/2.200/3.300/0.400 ms"
        ),
        stderr="",
        returncode=0,
    )

    result = probe_ping("gateway", "192.168.1.1", "wlp0s20f3", 6.0)

    values = _values(result)
    assert values["network.gateway_reachable"] is True
    assert values["network.gateway_packet_loss_percent"] == 0.0
    assert values["network.gateway_latency_ms"] == 2.2
    assert values["network.gateway_jitter_ms"] == 0.4
    assert result.errors == []


@patch("wifi_agent.collectors.connectivity.run_command")
def test_ping_loss_is_measurement_not_collector_error(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="4 packets transmitted, 0 received, 100% packet loss, time 3000ms",
        stderr="",
        returncode=1,
    )

    result = probe_ping("internet", "1.1.1.1", "wlp0s20f3", 6.0)

    values = _values(result)
    assert values["network.internet_reachable"] is False
    assert values["network.internet_packet_loss_percent"] == 100.0
    assert "network.internet_latency_ms" not in values
    assert result.errors == []


@patch("wifi_agent.collectors.connectivity.time.perf_counter", side_effect=[10.0, 10.025])
@patch("wifi_agent.collectors.connectivity.run_command")
def test_dns_probe_emits_resolver_latency(mock_run_command, _mock_clock) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="93.184.216.34 STREAM example.com",
        stderr="",
        returncode=0,
    )

    result = probe_dns("example.com", "wlp0s20f3", 5.0)

    values = _values(result)
    assert values["network.dns_success"] is True
    assert values["network.dns_latency_ms"] == 25.0


@patch("wifi_agent.collectors.connectivity.run_command")
def test_https_probe_emits_cumulative_transaction_timings(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="__WEM_HTTP_TIMING__:204|0.003|0.008|0.020|0.035|0.040",
        stderr="",
        returncode=0,
    )

    result = probe_https("https://example.com", "wlp0s20f3", 5.0)

    values = _values(result)
    assert values["network.https_success"] is True
    assert values["network.https_status_code"] == 204
    assert values["network.https_dns_ms"] == 3.0
    assert values["network.https_tcp_connect_ms"] == 8.0
    assert values["network.https_tls_handshake_ms"] == 20.0
    assert values["network.https_ttfb_ms"] == 35.0
    assert values["network.https_total_ms"] == 40.0


def test_network_probe_gauges_are_part_of_default_telemetry() -> None:
    aggregator = TelemetryAggregator(10.0)
    assert "network.gateway_latency_ms" in aggregator.metrics
    assert "network.gateway_packet_loss_percent" in aggregator.metrics
    assert "network.dns_latency_ms" in aggregator.metrics
    assert "network.internet_latency_ms" in aggregator.metrics
    assert "network.https_total_ms" in aggregator.metrics
