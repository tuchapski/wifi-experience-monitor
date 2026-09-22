from wem.diagnostics.engine import DiagnosticEngine
from wem.models.metrics import (
    ConnectivityMetrics,
    WifiDeltaMetrics,
    WifiMetrics,
)


def test_healthy_snapshot() -> None:
    engine = DiagnosticEngine()

    result = engine.analyze(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            associated=True,
            signal_dbm=-60,
            beacon_loss=0,
        ),
        wifi_delta=WifiDeltaMetrics(
            tx_retries_per_100_packets=5,
            tx_failed_percent=0,
        ),
        connectivity=ConnectivityMetrics(
            gateway_reachable=True,
            gateway_packet_loss_percent=0,
            gateway_latency_avg_ms=5,
            dns_success=True,
            dns_latency_ms=10,
            internet_reachable=True,
            internet_packet_loss_percent=0,
            internet_latency_avg_ms=20,
            https_success=True,
            https_total_time_ms=100,
        ),
    )

    assert result.overall_status == "healthy"
    assert result.probable_domain is None
    assert result.findings == []


def test_low_wifi_signal_warning() -> None:
    engine = DiagnosticEngine()

    result = engine.analyze(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            associated=True,
            signal_dbm=-78,
        ),
        wifi_delta=None,
        connectivity=ConnectivityMetrics(),
    )

    assert result.overall_status == "warning"
    assert result.probable_domain == "wifi"

    assert any(finding.code == "WIFI_LOW_SIGNAL" for finding in result.findings)


def test_very_low_wifi_signal_is_critical() -> None:
    engine = DiagnosticEngine()

    result = engine.analyze(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            associated=True,
            signal_dbm=-85,
        ),
        wifi_delta=None,
        connectivity=ConnectivityMetrics(),
    )

    assert result.overall_status == "critical"
    assert result.probable_domain == "wifi"

    assert any(finding.code == "WIFI_VERY_LOW_SIGNAL" for finding in result.findings)


def test_high_wifi_retries() -> None:
    engine = DiagnosticEngine()

    result = engine.analyze(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            associated=True,
            signal_dbm=-60,
        ),
        wifi_delta=WifiDeltaMetrics(
            tx_retries_per_100_packets=55,
        ),
        connectivity=ConnectivityMetrics(),
    )

    assert result.overall_status == "critical"
    assert result.probable_domain == "wifi"


def test_gateway_failure() -> None:
    engine = DiagnosticEngine()

    result = engine.analyze(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            associated=True,
            signal_dbm=-60,
        ),
        wifi_delta=None,
        connectivity=ConnectivityMetrics(
            gateway_reachable=False,
        ),
    )

    assert result.overall_status == "warning"
    assert result.probable_domain == "gateway"

    assert any(finding.code == "GATEWAY_ICMP_FAILED" for finding in result.findings)


def test_dns_failure() -> None:
    engine = DiagnosticEngine()

    result = engine.analyze(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            associated=True,
            signal_dbm=-60,
        ),
        wifi_delta=None,
        connectivity=ConnectivityMetrics(
            gateway_reachable=True,
            dns_success=False,
        ),
    )

    assert result.overall_status == "critical"
    assert result.probable_domain == "dns"


def test_https_failure() -> None:
    engine = DiagnosticEngine()

    result = engine.analyze(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            associated=True,
            signal_dbm=-60,
        ),
        wifi_delta=None,
        connectivity=ConnectivityMetrics(
            gateway_reachable=True,
            dns_success=True,
            internet_reachable=True,
            https_success=False,
        ),
    )

    assert result.overall_status == "critical"
    assert result.probable_domain == "application"
