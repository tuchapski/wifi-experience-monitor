from wem.incidents.engine import IncidentEngine
from wem.models.metrics import DiagnosticFinding, DiagnosticResult


def diagnostic(*findings: DiagnosticFinding) -> DiagnosticResult:
    return DiagnosticResult(
        overall_status="warning" if findings else "healthy",
        probable_domain="baseline" if findings else None,
        findings=list(findings),
    )


def finding(code: str) -> DiagnosticFinding:
    return DiagnosticFinding("warning", "baseline", code, "baseline deviation")


def test_fresh_codes_prevent_unmeasured_baseline_metric_from_recovering():
    engine = IncidentEngine(warning_open_samples=1, resolve_samples=1)
    code = "BASELINE_DNS_LATENCY_DEVIATION"
    opened = engine.evaluate(diagnostic(finding(code)), fresh_codes={code})
    assert len(opened.active_incidents) == 1

    unrelated = engine.evaluate(
        diagnostic(),
        fresh_codes={"BASELINE_RSSI_DEVIATION"},
    )
    assert len(unrelated.active_incidents) == 1
    assert unrelated.events == []

    recovered = engine.evaluate(diagnostic(), fresh_codes={code})
    assert recovered.active_incidents == []
    assert recovered.events[0].action == "resolved"
