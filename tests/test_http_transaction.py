from unittest.mock import patch

from wem.collectors.command import CommandResult
from wem.tests_engine.http_transaction import probe_http_transaction


@patch("wem.tests_engine.http_transaction.run_command")
def test_https_transaction_exposes_cumulative_milestones(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="__WEM_HTTP_TIMING__:204|0.003|0.008|0.020|0.035|0.040",
        stderr="",
        returncode=0,
    )

    result = probe_http_transaction("https://portal.example.com/health", 5.0)

    assert result.status == "passed"
    assert result.status_code == 204
    assert result.dns_ms == 3.0
    assert result.tcp_connect_ms == 8.0
    assert result.tls_handshake_ms == 20.0
    assert result.ttfb_ms == 35.0
    assert result.total_ms == 40.0
    command = mock_run_command.call_args.args[0]
    assert command[0] == "curl"
    assert "--write-out" in command
    assert mock_run_command.call_args.kwargs["timeout"] == 6.0


@patch("wem.tests_engine.http_transaction.run_command")
def test_plain_http_leaves_tls_unavailable(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="__WEM_HTTP_TIMING__:200|0.002|0.006|0.000|0.010|0.012",
        stderr="",
        returncode=0,
    )

    result = probe_http_transaction("http://portal.example.com/health", 3.0)

    assert result.status == "passed"
    assert result.tls_handshake_ms is None
    assert result.total_ms == 12.0


@patch("wem.tests_engine.http_transaction.run_command")
def test_transport_failure_preserves_partial_timings(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="__WEM_HTTP_TIMING__:000|0.004|0.000|0.000|0.000|2.000",
        stderr="curl: (6) Could not resolve host",
        returncode=6,
    )

    result = probe_http_transaction("https://missing.example.com", 2.0)

    assert result.status == "failed"
    assert result.status_code is None
    assert result.dns_ms == 4.0
    assert result.tcp_connect_ms is None
    assert result.total_ms == 2000.0


@patch("wem.tests_engine.http_transaction.run_command")
def test_missing_curl_is_collection_error(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="",
        stderr="No such file or directory: curl",
        returncode=127,
    )

    result = probe_http_transaction("https://portal.example.com", 2.0)

    assert result.status == "error"
    assert result.total_ms is None
    assert "collection error" in result.reason.lower()
