from wem.analysis.adaptive_baseline import AdaptiveBaselineEngine
from wem.models.metrics import (
    CalibrationResult,
    ConnectionCycleSloMetrics,
    ConnectivityMetrics,
    NetworkMetrics,
    SensorHealthMetrics,
    SensorSnapshot,
    WifiDeltaMetrics,
    WifiMetrics,
)
from wem.models.metrics import (
    TestOutcome as Outcome,
)
from wem.profiles.models import (
    AdaptiveBaselineThresholds,
)
from wem.profiles.models import (
    TestProfileConfig as ProfileConfiguration,
)


def snapshot(*, signal: int = -60, gateway_ms: float = 10.0) -> SensorSnapshot:
    result = SensorSnapshot.create(
        health=SensorHealthMetrics("wlan0"),
        calibration=CalibrationResult("calibrated", True),
        wifi=WifiMetrics("wlan0", ssid="CORP", signal_dbm=signal),
        network=NetworkMetrics("wlan0"),
        connectivity=ConnectivityMetrics(
            tests={"gateway": Outcome("passed", "fresh", fresh=True)},
            gateway_latency_avg_ms=gateway_ms,
        ),
        wifi_delta=WifiDeltaMetrics(tx_retries_per_100_packets=5.0),
    )
    result.connection_cycle_slo = ConnectionCycleSloMetrics(
        status="healthy",
        sample_count=5,
        minimum_samples=5,
        window_size=20,
        p95_ms=1000.0,
        warning_threshold_ms=8000.0,
        critical_threshold_ms=15000.0,
        latest_cycle_ms=900.0,
        fresh=True,
        reason="fixture",
    )
    return result


def thresholds() -> AdaptiveBaselineThresholds:
    return AdaptiveBaselineThresholds(
        lookback_hours=24,
        minimum_samples=10,
        max_samples=30,
        warning_sigma=2.0,
        critical_sigma=4.0,
    )


def test_robust_baseline_detects_directional_degradation():
    engine = AdaptiveBaselineEngine(thresholds())
    current = snapshot(signal=-72, gateway_ms=20.0)
    reference = {
        "signal_dbm": [-60.0, -61.0, -60.0, -59.0, -60.0] * 2,
        "gateway_latency_avg_ms": [10.0, 11.0, 9.0, 10.0, 10.0] * 2,
    }

    engine.seed("CORP", reference)
    result = engine.evaluate(current)

    by_key = {item.key: item for item in result.metrics.metrics}
    assert by_key["signal_dbm"].status == "critical"
    assert by_key["gateway_latency_avg_ms"].status == "critical"
    assert {finding.code for finding in result.findings} == {
        "BASELINE_RSSI_DEVIATION",
        "BASELINE_GATEWAY_LATENCY_DEVIATION",
    }
    assert result.metrics.status == "critical"


def test_cached_test_value_is_not_treated_as_fresh_measurement():
    engine = AdaptiveBaselineEngine(thresholds())
    current = snapshot(gateway_ms=500.0)
    current.connectivity.tests["gateway"].fresh = False
    reference = {"gateway_latency_avg_ms": [10.0] * 10}

    engine.seed("CORP", reference)
    result = engine.evaluate(current)
    gateway = next(item for item in result.metrics.metrics if item.key == "gateway_latency_avg_ms")

    assert gateway.status == "unavailable"
    assert "BASELINE_GATEWAY_LATENCY_DEVIATION" not in result.fresh_codes
    assert result.findings == []


def test_insufficient_history_does_not_create_findings():
    engine = AdaptiveBaselineEngine(thresholds())
    engine.seed("CORP", {"signal_dbm": [-60.0, -61.0]})
    result = engine.evaluate(snapshot())

    rssi = next(item for item in result.metrics.metrics if item.key == "signal_dbm")
    assert rssi.status == "insufficient_data"
    assert result.findings == []
    assert result.metrics.status == "insufficient_data"


def test_profile_defaults_enable_adaptive_baseline_without_breaking_old_json():
    profile = ProfileConfiguration.model_validate({})
    baseline = profile.thresholds.adaptive_baseline

    assert baseline.enabled is True
    assert baseline.lookback_hours == 24
    assert baseline.minimum_samples == 30
    assert baseline.warning_sigma == 3.5
    assert baseline.critical_sigma == 6.0
