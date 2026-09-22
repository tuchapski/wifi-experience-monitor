from wem.analysis.recommendations import RecommendationEngine
from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    DiagnosticFinding,
    DiagnosticResult,
    EnvironmentChange,
    WifiMetrics,
)


def _calibration(calibrated: bool = True) -> CalibrationResult:
    return CalibrationResult(status="healthy" if calibrated else "warning", calibrated=calibrated)


def test_recommendations_are_explainable_and_deduplicated():
    diagnostic = DiagnosticResult(
        overall_status="critical",
        probable_domain="wifi",
        findings=[
            DiagnosticFinding("critical", "wifi", "WIFI_HIGH_RETRIES", "retry evidence"),
            DiagnosticFinding("critical", "wifi", "WIFI_HIGH_RETRIES", "duplicate evidence"),
        ],
    )
    recommendations = RecommendationEngine().build(
        diagnostic, _calibration(), WifiMetrics("wlan0"), None, ConnectivityMetrics(), []
    )
    assert [item.code for item in recommendations] == ["WIFI_HIGH_RETRIES"]
    assert recommendations[0].action
    assert recommendations[0].evidence == "retry evidence"


def test_incomplete_calibration_produces_calibration_guidance():
    recommendations = RecommendationEngine().build(
        DiagnosticResult("unknown", None, complete=False),
        _calibration(False),
        WifiMetrics("wlan0"),
        None,
        ConnectivityMetrics(),
        [],
    )
    assert recommendations[0].code == "CALIBRATION_INCOMPLETE"
    assert recommendations[0].severity == "info"


def test_bssid_change_produces_correlation_guidance():
    change = EnvironmentChange(
        code="WIFI_BSSID_CHANGED",
        field="BSSID",
        previous="aa:bb:cc:dd:ee:ff",
        current="11:22:33:44:55:66",
        message="Access point changed.",
    )
    recommendations = RecommendationEngine().build(
        DiagnosticResult("healthy", None),
        _calibration(),
        WifiMetrics("wlan0"),
        None,
        ConnectivityMetrics(),
        [change],
    )
    assert recommendations[0].code == "CORRELATE_AP_CHANGE"


def test_unknown_diagnostic_finding_does_not_create_speculative_action():
    recommendations = RecommendationEngine().build(
        DiagnosticResult(
            "warning",
            "unknown",
            findings=[DiagnosticFinding("warning", "unknown", "NEW_CODE", "not mapped")],
        ),
        _calibration(),
        WifiMetrics("wlan0"),
        None,
        ConnectivityMetrics(),
        [],
    )
    assert recommendations == []
