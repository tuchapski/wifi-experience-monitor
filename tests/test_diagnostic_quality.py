from unittest.mock import patch

import pytest

from wem.calibration.engine import CalibrationEngine
from wem.collectors.command import CommandResult, run_command
from wem.diagnostics.engine import DiagnosticEngine
from wem.incidents.engine import IncidentEngine
from wem.models.metrics import (
    ConnectivityMetrics,
    DiagnosticFinding,
    DiagnosticResult,
    SensorHealthMetrics,
    WifiMetrics,
)
from wem.runtime.sensor import RuntimeConfig, SensorRuntime
from wem.tests_engine.connectivity import ConnectivityTester


def test_missing_ping_binary_is_collection_error():
    with patch("wem.collectors.command.subprocess.run", side_effect=FileNotFoundError("ping")):
        assert run_command(["ping"]).returncode == 127
    tester = ConnectivityTester("wlan0", "192.0.2.1")
    metrics = ConnectivityMetrics()
    with patch(
        "wem.tests_engine.connectivity.run_command",
        return_value=CommandResult("", "Permission denied", 2),
    ):
        tester._test_gateway(metrics)
    assert metrics.gateway_reachable is None
    assert metrics.gateway_packet_loss_percent is None
    assert metrics.tests["gateway"].status == "error"


def test_actual_packet_loss_is_failed_test():
    tester = ConnectivityTester("wlan0", "192.0.2.1")
    metrics = ConnectivityMetrics()
    with patch(
        "wem.tests_engine.connectivity.run_command",
        return_value=CommandResult("4 packets transmitted, 0 received, 100% packet loss", "", 1),
    ):
        tester._test_gateway(metrics)
    assert metrics.gateway_reachable is False
    assert metrics.gateway_packet_loss_percent == 100
    assert metrics.tests["gateway"].status == "failed"
    assert tester.errors == []


def test_empty_measurements_are_not_healthy():
    result = DiagnosticEngine().analyze(WifiMetrics("wlan0"), None, ConnectivityMetrics())
    assert result.overall_status == "unknown"
    assert result.probable_domain is None
    assert result.complete is False


@pytest.mark.parametrize("evidence", [{"dns_success": True}, {"https_success": True}, {}])
def test_external_ping_failure_does_not_claim_internet_outage(evidence):
    result = DiagnosticEngine().analyze(
        WifiMetrics("wlan0", associated=True, signal_dbm=-60),
        None,
        ConnectivityMetrics(internet_reachable=False, **evidence),
    )
    assert result.overall_status == "warning"
    assert result.findings[0].code == "INTERNET_ICMP_FAILED"
    assert not any(f.code == "INTERNET_UNREACHABLE" for f in result.findings)


def test_calibration_reports_unknown_without_claiming_missing_interface():
    result = CalibrationEngine().analyze(SensorHealthMetrics("wlan0"))
    assert not result.calibrated
    assert result.status == "inconclusive"
    assert result.checks["interface_exists"].status == "unavailable"
    assert not any(f.code == "INTERFACE_NOT_FOUND" for f in result.findings)


def test_calibration_complete_and_critical_cases():
    health = SensorHealthMetrics(
        "wlan0",
        interface_exists=True,
        interface_up=True,
        wireless_interface=True,
        driver="iwlwifi",
        firmware_version="test",
        rfkill_soft_blocked=False,
        rfkill_hard_blocked=False,
        network_manager_managed=True,
        power_save=False,
    )
    assert CalibrationEngine().analyze(health).calibrated
    health.interface_exists = False
    result = CalibrationEngine().analyze(health)
    assert result.status == "critical"
    assert not result.calibrated


def test_incomplete_samples_do_not_resolve_incidents():
    engine = IncidentEngine(critical_open_samples=1, resolve_samples=2)
    fault = DiagnosticResult(
        "critical", "dns", findings=[DiagnosticFinding("critical", "dns", "DNS_FAILURE", "failed")]
    )
    engine.evaluate(fault)
    engine.evaluate(DiagnosticResult("healthy", None))
    for _ in range(4):
        result = engine.evaluate(DiagnosticResult("unknown", None, complete=False))
        assert len(result.active_incidents) == 1
        assert result.events == []
    assert engine.evaluate(DiagnosticResult("healthy", None)).active_incidents
    assert not engine.evaluate(DiagnosticResult("healthy", None)).active_incidents


def test_invalid_interface_skips_all_synthetic_tests():
    with (
        patch("wem.runtime.sensor.SensorHealthCollector") as health,
        patch("wem.runtime.sensor.WifiCollector") as wifi,
        patch("wem.runtime.sensor.NetworkCollector") as network,
        patch("wem.runtime.sensor.ConnectivityTester") as tester,
    ):
        from wem.models.metrics import NetworkMetrics

        health.return_value.collect.return_value = SensorHealthMetrics(
            "missing",
            interface_exists=False,
        )
        wifi.return_value.collect.return_value = WifiMetrics("missing")
        network.return_value.collect.return_value = NetworkMetrics("missing")
        for collector in (health, wifi, network, tester):
            collector.return_value.errors = []
        snapshot = SensorRuntime(RuntimeConfig("missing")).collect_once()
        tester.return_value.run.assert_not_called()
        assert all(item.status == "skipped" for item in snapshot.connectivity.tests.values())
        assert snapshot.diagnostic.probable_domain == "sensor"
        assert snapshot.diagnostic.complete is False


def test_low_signal_has_no_duplicate_findings():
    result = DiagnosticEngine().analyze(
        WifiMetrics("wlan0", signal_dbm=-78),
        None,
        ConnectivityMetrics(),
    )
    assert [f.code for f in result.findings].count("WIFI_LOW_SIGNAL") == 1
