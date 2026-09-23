from unittest.mock import MagicMock, patch

from wem.collectors.command import CommandResult
from wem.models.metrics import ConnectivityMetrics
from wem.profiles.models import (
    ApplicationTargetConfig,
)
from wem.profiles.models import (
    TestConfigurations as ConnectivityConfigurations,
)
from wem.tests_engine.connectivity import ConnectivityTester
from wem.tests_engine.http_transaction import HttpTransactionResult

PING_SUCCESS_OUTPUT = """
PING target (192.168.15.1) 56(84) bytes of data.
64 bytes from target: icmp_seq=1 ttl=64 time=9.8 ms
64 bytes from target: icmp_seq=2 ttl=64 time=10.5 ms
64 bytes from target: icmp_seq=3 ttl=64 time=11.2 ms
64 bytes from target: icmp_seq=4 ttl=64 time=10.5 ms

--- target ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 603ms
rtt min/avg/max/mdev = 9.800/10.500/11.200/0.500 ms
"""


@patch("wem.tests_engine.connectivity.probe_http_transaction")
@patch("wem.tests_engine.connectivity.socket.getaddrinfo")
@patch("wem.tests_engine.connectivity.run_command")
def test_connectivity_tester_success(
    mock_run_command,
    mock_getaddrinfo,
    mock_http_probe,
) -> None:
    mock_run_command.return_value = CommandResult(
        stdout=PING_SUCCESS_OUTPUT,
        stderr="",
        returncode=0,
    )

    mock_getaddrinfo.return_value = [
        (
            2,
            1,
            6,
            "",
            ("104.20.23.154", 0),
        )
    ]
    mock_http_probe.return_value = HttpTransactionResult(
        status="passed",
        reason="HTTP response: 200.",
        status_code=200,
        dns_ms=3.0,
        tcp_connect_ms=8.0,
        tls_handshake_ms=20.0,
        ttfb_ms=35.0,
        total_ms=40.0,
    )

    tester = ConnectivityTester(
        interface="wlp0s20f3",
        gateway="192.168.15.1",
    )

    metrics = tester.run()

    assert metrics.gateway_reachable is True
    assert metrics.gateway_packet_loss_percent == 0.0
    assert metrics.gateway_latency_min_ms == 9.8
    assert metrics.gateway_latency_avg_ms == 10.5
    assert metrics.gateway_latency_max_ms == 11.2
    assert metrics.gateway_jitter_ms == 0.5

    assert metrics.dns_success is True
    assert metrics.dns_result == "104.20.23.154"

    assert metrics.internet_reachable is True
    assert metrics.internet_packet_loss_percent == 0.0
    assert metrics.internet_latency_min_ms == 9.8
    assert metrics.internet_latency_avg_ms == 10.5
    assert metrics.internet_latency_max_ms == 11.2
    assert metrics.internet_jitter_ms == 0.5

    assert metrics.https_success is True
    assert metrics.https_status_code == 200
    assert metrics.https_dns_ms == 3.0
    assert metrics.https_tcp_connect_ms == 8.0
    assert metrics.https_tls_handshake_ms == 20.0
    assert metrics.https_ttfb_ms == 35.0
    assert metrics.https_total_time_ms == 40.0

    assert tester.errors == []


@patch("wem.tests_engine.connectivity.run_command")
def test_connectivity_tester_gateway_failure(
    mock_run_command,
) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="",
        stderr="timeout",
        returncode=1,
    )

    tester = ConnectivityTester(
        interface="wlp0s20f3",
        gateway="192.168.15.1",
    )

    (
        success,
        packet_loss,
        latency_min,
        latency_avg,
        latency_max,
        jitter,
    ) = tester._ping("192.168.15.1")

    assert success is None
    assert packet_loss is None
    assert latency_min is None
    assert latency_avg is None
    assert latency_max is None
    assert jitter is None


def test_connectivity_tester_without_gateway() -> None:
    tester = ConnectivityTester(
        interface="wlp0s20f3",
        gateway=None,
    )

    metrics = ConnectivityMetrics()

    tester._test_gateway(metrics)

    assert metrics.gateway_reachable is None
    assert metrics.gateway_packet_loss_percent is None
    assert metrics.gateway_latency_min_ms is None
    assert metrics.gateway_latency_avg_ms is None
    assert metrics.gateway_latency_max_ms is None
    assert metrics.gateway_jitter_ms is None

    assert tester.errors == []
    assert metrics.tests["gateway"].status == "skipped"


@patch(
    "wem.tests_engine.connectivity.socket.getaddrinfo",
    side_effect=OSError("dns failure"),
)
def test_connectivity_tester_dns_failure(
    mock_getaddrinfo,
) -> None:
    del mock_getaddrinfo

    tester = ConnectivityTester(
        interface="wlp0s20f3",
        gateway="192.168.15.1",
    )

    metrics = ConnectivityMetrics()

    tester._test_dns(metrics)

    assert metrics.dns_success is False
    assert metrics.dns_result is None
    assert metrics.dns_latency_ms is not None

    assert tester.errors == []
    assert metrics.tests["dns"].status == "failed"
    assert "dns failure" in metrics.tests["dns"].reason


@patch("wem.tests_engine.connectivity.run_command")
def test_profile_controls_dns_timeout(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="203.0.113.10 STREAM example.com",
        stderr="",
        returncode=0,
    )
    tests = ConnectivityConfigurations()
    tests.dns.timeout_seconds = 1.5
    tester = ConnectivityTester("wlan0", "192.0.2.1", tests=tests)
    metrics = tester.run_test("dns")

    mock_run_command.assert_called_once_with(["getent", "ahostsv4", "example.com"], timeout=1.5)
    assert metrics.dns_success is True
    assert metrics.dns_result == "203.0.113.10"


@patch("wem.tests_engine.connectivity.run_command")
def test_profile_can_override_automatic_gateway(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout=PING_SUCCESS_OUTPUT,
        stderr="",
        returncode=0,
    )
    tests = ConnectivityConfigurations()
    tests.gateway.automatic_gateway = False
    tests.gateway.target = "192.0.2.254"
    tests.gateway.timeout_seconds = 9
    tester = ConnectivityTester("wlan0", "192.0.2.1", tests=tests)

    metrics = tester.run_test("gateway")

    command = mock_run_command.call_args.args[0]
    assert command[-1] == "192.0.2.254"
    assert mock_run_command.call_args.kwargs["timeout"] == 9
    assert metrics.gateway_reachable is True


@patch("wem.tests_engine.connectivity.probe_http_transaction")
def test_http_application_target_records_status_and_latency(mock_http_probe) -> None:
    mock_http_probe.return_value = HttpTransactionResult(
        status="passed",
        reason="HTTP response: 204.",
        status_code=204,
        dns_ms=4.0,
        tcp_connect_ms=9.0,
        tls_handshake_ms=22.0,
        ttfb_ms=41.0,
        total_ms=45.0,
    )
    tester = ConnectivityTester("wlan0", "192.0.2.1")
    target = ApplicationTargetConfig(
        name="Portal",
        kind="http",
        target="https://portal.example.com/health",
        interval_seconds=10,
        timeout_seconds=3,
    )

    metric = tester.run_application_target(target)

    assert metric.status == "passed"
    assert metric.status_code == 204
    assert metric.latency_ms == 45.0
    assert metric.dns_ms == 4.0
    assert metric.tcp_connect_ms == 9.0
    assert metric.tls_handshake_ms == 22.0
    assert metric.ttfb_ms == 41.0
    assert metric.scope == "host"


@patch("wem.tests_engine.connectivity.socket.create_connection")
def test_tcp_application_target(mock_create_connection) -> None:
    connection = MagicMock()
    mock_create_connection.return_value.__enter__.return_value = connection
    tester = ConnectivityTester("wlan0", "192.0.2.1")
    target = ApplicationTargetConfig(
        name="Database",
        kind="tcp",
        target="db.example.com",
        port=5432,
        interval_seconds=10,
        timeout_seconds=2,
    )

    metric = tester.run_application_target(target)

    assert metric.status == "passed"
    assert metric.port == 5432
    assert metric.latency_ms is not None
    mock_create_connection.assert_called_once_with(("db.example.com", 5432), timeout=2.0)


@patch("wem.tests_engine.connectivity.run_command")
def test_dns_application_target(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="203.0.113.50 STREAM api.example.com\n",
        stderr="",
        returncode=0,
    )
    tester = ConnectivityTester("wlan0", "192.0.2.1")
    target = ApplicationTargetConfig(
        name="API DNS",
        kind="dns",
        target="api.example.com",
        interval_seconds=10,
        timeout_seconds=2,
    )

    metric = tester.run_application_target(target)

    assert metric.status == "passed"
    assert metric.latency_ms is not None
    assert "203.0.113.50" in metric.reason
    mock_run_command.assert_called_once_with(["getent", "ahostsv4", "api.example.com"], timeout=2.0)
