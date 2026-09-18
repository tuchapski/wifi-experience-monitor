from unittest.mock import MagicMock, patch

from wem.collectors.command import CommandResult
from wem.tests_engine.connectivity import ConnectivityTester


@patch("wem.tests_engine.connectivity.urllib.request.urlopen")
@patch("wem.tests_engine.connectivity.socket.getaddrinfo")
@patch("wem.tests_engine.connectivity.run_command")
def test_connectivity_tester_success(
    mock_run_command,
    mock_getaddrinfo,
    mock_urlopen,
) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="64 bytes from host: time=10.5 ms",
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

    response = MagicMock()
    response.status = 200

    mock_urlopen.return_value.__enter__.return_value = response

    tester = ConnectivityTester(
        interface="wlp0s20f3",
        gateway="192.168.15.1",
    )

    metrics = tester.run()

    assert metrics.gateway_reachable is True
    assert metrics.gateway_latency_ms == 10.5

    assert metrics.dns_success is True
    assert metrics.dns_result == "104.20.23.154"

    assert metrics.internet_reachable is True
    assert metrics.internet_latency_ms == 10.5

    assert metrics.https_success is True
    assert metrics.https_status_code == 200

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

    success, latency = tester._ping("192.168.15.1")

    assert success is False
    assert latency is None


def test_connectivity_tester_without_gateway() -> None:
    tester = ConnectivityTester(
        interface="wlp0s20f3",
        gateway=None,
    )

    from wem.models.metrics import ConnectivityMetrics

    metrics = ConnectivityMetrics()

    tester._test_gateway(metrics)

    assert metrics.gateway_reachable is None
    assert metrics.gateway_latency_ms is None

    assert tester.errors == ["gateway test skipped: no gateway configured"]


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

    from wem.models.metrics import ConnectivityMetrics

    metrics = ConnectivityMetrics()

    try:
        tester._test_dns(metrics)
    except OSError:
        pass
