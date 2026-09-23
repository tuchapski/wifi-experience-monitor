from wem.analysis.correlation import CorrelationEngine
from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    DiagnosticFinding,
    DiagnosticResult,
    NetworkMetrics,
    SensorHealthMetrics,
    SensorSnapshot,
    WifiMetrics,
)


def snapshot(*findings: DiagnosticFinding, complete: bool = True) -> SensorSnapshot:
    result = SensorSnapshot.create(
        health=SensorHealthMetrics("wlan0"),
        calibration=CalibrationResult("healthy", True),
        wifi=WifiMetrics("wlan0", associated=True, signal_dbm=-60),
        network=NetworkMetrics("wlan0"),
        connectivity=ConnectivityMetrics(),
    )
    result.diagnostic = DiagnosticResult(
        overall_status="warning" if findings else "healthy",
        probable_domain=findings[0].domain if findings else None,
        complete=complete,
        findings=list(findings),
    )
    return result


def finding(severity: str, domain: str, code: str) -> DiagnosticFinding:
    return DiagnosticFinding(severity, domain, code, f"evidence for {code}")


def test_healthy_complete_snapshot_has_no_correlated_degradation():
    assessment = CorrelationEngine().evaluate(snapshot())
    assert assessment.status == "no_degradation"
    assert assessment.primary_domain is None
    assert assessment.hypotheses == []


def test_dns_current_failure_and_service_slo_converge_to_strong_dns():
    value = snapshot(
        finding("critical", "dns", "DNS_FAILURE"),
        finding("warning", "service_slo", "SERVICE_SLO_DNS"),
    )
    value.connectivity.gateway_reachable = True
    value.connectivity.internet_reachable = True

    assessment = CorrelationEngine().evaluate(value)

    assert assessment.status == "correlated"
    assert assessment.primary_domain == "dns"
    assert assessment.hypotheses[0].support == "strong"
    assert {item.source for item in assessment.hypotheses[0].evidence} >= {
        "current_diagnostic",
        "rolling_service_slo",
        "isolation",
    }


def test_application_current_signal_with_healthy_upstream_is_moderate():
    value = snapshot(finding("warning", "application", "HTTPS_HIGH_RESPONSE_TIME"))
    value.connectivity.dns_success = True
    value.connectivity.internet_reachable = True

    assessment = CorrelationEngine().evaluate(value)

    assert assessment.primary_domain == "application"
    assert assessment.hypotheses[0].support == "moderate"


def test_equal_support_across_domains_is_ambiguous():
    value = snapshot(
        finding("warning", "dns", "DNS_HIGH_LATENCY"),
        finding("warning", "application", "HTTPS_HIGH_RESPONSE_TIME"),
    )

    assessment = CorrelationEngine().evaluate(value)

    assert assessment.status == "ambiguous"
    assert assessment.primary_domain is None
    assert {item.domain for item in assessment.hypotheses} == {"dns", "application"}


def test_stage_ipv4_slo_maps_to_local_network():
    value = snapshot(finding("warning", "connection_cycle", "CONNECTION_CYCLE_IPV4_P95_SLO"))

    assessment = CorrelationEngine().evaluate(value)

    assert assessment.primary_domain == "local_network"
    assert assessment.hypotheses[0].evidence[0].source == "connection_cycle_slo"


def test_collection_only_incomplete_state_remains_insufficient():
    value = snapshot(
        finding("warning", "sensor", "COLLECTION_ERROR"),
        complete=False,
    )
    value.collector_errors = ["iw failed"]

    assessment = CorrelationEngine().evaluate(value)

    assert assessment.status == "insufficient_data"
    assert assessment.primary_domain is None
    assert assessment.hypotheses == []
