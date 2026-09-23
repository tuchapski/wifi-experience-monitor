from wem.incidents.engine import (
    IncidentEngine,
)
from wem.models.metrics import (
    DiagnosticFinding,
    DiagnosticResult,
)


def diagnostic_with_finding(
    severity: str = "warning",
    code: str = "WIFI_LOW_SIGNAL",
) -> DiagnosticResult:
    return DiagnosticResult(
        overall_status=severity,
        probable_domain="wifi",
        findings=[
            DiagnosticFinding(
                severity=severity,
                domain="wifi",
                code=code,
                message="Test finding",
            )
        ],
    )


def healthy_diagnostic() -> DiagnosticResult:
    return DiagnosticResult(
        overall_status="healthy",
        probable_domain=None,
        findings=[],
    )


def test_warning_requires_three_samples() -> None:
    engine = IncidentEngine()

    first = engine.evaluate(
        diagnostic_with_finding(),
        timestamp="2026-09-18T10:00:00+00:00",
    )

    second = engine.evaluate(
        diagnostic_with_finding(),
        timestamp="2026-09-18T10:00:05+00:00",
    )

    third = engine.evaluate(
        diagnostic_with_finding(),
        timestamp="2026-09-18T10:00:10+00:00",
    )

    assert first.active_incidents == []

    assert second.active_incidents == []

    assert len(third.active_incidents) == 1

    assert third.events[0].action == "opened"


def test_critical_requires_two_samples() -> None:
    engine = IncidentEngine()

    first = engine.evaluate(
        diagnostic_with_finding(
            severity="critical",
            code="GATEWAY_UNREACHABLE",
        ),
        timestamp="2026-09-18T10:00:00+00:00",
    )

    second = engine.evaluate(
        diagnostic_with_finding(
            severity="critical",
            code="GATEWAY_UNREACHABLE",
        ),
        timestamp="2026-09-18T10:00:05+00:00",
    )

    assert first.active_incidents == []

    assert len(second.active_incidents) == 1

    assert second.events[0].action == "opened"


def test_single_warning_does_not_open_incident() -> None:
    engine = IncidentEngine()

    engine.evaluate(
        diagnostic_with_finding(),
    )

    result = engine.evaluate(healthy_diagnostic())

    assert result.active_incidents == []

    assert result.events == []


def test_incident_resolves_after_three_samples() -> None:
    engine = IncidentEngine()

    for index in range(3):
        engine.evaluate(
            diagnostic_with_finding(),
            timestamp=(f"2026-09-18T10:00:{index * 5:02d}+00:00"),
        )

    first_recovery = engine.evaluate(
        healthy_diagnostic(),
        timestamp=("2026-09-18T10:00:15+00:00"),
    )

    second_recovery = engine.evaluate(
        healthy_diagnostic(),
        timestamp=("2026-09-18T10:00:20+00:00"),
    )

    third_recovery = engine.evaluate(
        healthy_diagnostic(),
        timestamp=("2026-09-18T10:00:25+00:00"),
    )

    assert len(first_recovery.active_incidents) == 1

    assert len(second_recovery.active_incidents) == 1

    assert third_recovery.active_incidents == []

    assert len(third_recovery.events) == 1

    assert third_recovery.events[0].action == "resolved"


def test_recovery_counter_resets_if_problem_returns() -> None:
    engine = IncidentEngine()

    for _ in range(3):
        engine.evaluate(diagnostic_with_finding())

    engine.evaluate(healthy_diagnostic())

    result = engine.evaluate(diagnostic_with_finding())

    assert len(result.active_incidents) == 1

    assert result.events == []


def test_info_does_not_create_incident() -> None:
    engine = IncidentEngine()

    result = engine.evaluate(
        DiagnosticResult(
            overall_status="info",
            probable_domain="wifi",
            findings=[
                DiagnosticFinding(
                    severity="info",
                    domain="wifi",
                    code="WIFI_ROAM_DETECTED",
                    message="Roam detected",
                )
            ],
        )
    )

    assert result.active_incidents == []

    assert result.events == []


def test_cached_finding_does_not_advance_incident_confirmation() -> None:
    engine = IncidentEngine(critical_open_samples=2)
    diagnostic = DiagnosticResult(
        overall_status="critical",
        probable_domain="dns",
        findings=[
            DiagnosticFinding(
                severity="critical",
                domain="dns",
                code="DNS_FAILURE",
                message="DNS failed",
            )
        ],
    )

    first = engine.evaluate(diagnostic, fresh_domains={"dns"})
    cached = engine.evaluate(diagnostic, fresh_domains={"wifi"})
    second_execution = engine.evaluate(diagnostic, fresh_domains={"dns"})

    assert first.active_incidents == []
    assert cached.active_incidents == []
    assert len(second_execution.active_incidents) == 1
    assert second_execution.events[0].action == "opened"


def test_restore_active_incident() -> None:
    engine = IncidentEngine()

    engine.restore_active_incident(
        code="WIFI_LOW_SIGNAL",
        domain="wifi",
        severity="warning",
        message="Low signal",
        first_seen_at=("2026-09-18T10:00:00+00:00"),
        opened_at=("2026-09-18T10:00:10+00:00"),
    )

    result = engine.evaluate(diagnostic_with_finding())

    assert len(result.active_incidents) == 1

    assert result.events == []
