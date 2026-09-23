import pytest
from pydantic import ValidationError

from wem.analysis.connection_cycle_slo import ConnectionCycleSloEngine
from wem.models.metrics import ConnectionCycleMetrics, ConnectionStageMetric
from wem.profiles.models import (
    ConnectionCycleStageThresholds,
    ConnectionCycleThresholds,
    ConnectionStageP95Threshold,
)
from wem.profiles.models import (
    TestProfileConfig as ProfileConfiguration,
)


def cycle(
    session_id: str,
    duration_ms: float | None,
    *,
    session_type: str = "reconnect",
    state: str = "ready",
    stages: dict[str, float] | None = None,
):
    return ConnectionCycleMetrics(
        session_id=session_id,
        session_type=session_type,
        state=state,
        ssid="CORP",
        bssid="aa:bb:cc:dd:ee:ff",
        started_at="2026-09-22T12:00:00+00:00",
        last_observed_at="2026-09-22T12:00:05+00:00",
        completed_at=None,
        total_time_ms=duration_ms,
        sample_resolution_ms=5000.0,
        stages={
            key: ConnectionStageMetric(
                status="observed",
                elapsed_ms=value,
                reason="Observed for test.",
            )
            for key, value in (stages or {}).items()
        },
    )


def thresholds() -> ConnectionCycleThresholds:
    return ConnectionCycleThresholds(
        window_size=5,
        minimum_samples=3,
        p95_warning_ms=1000.0,
        p95_critical_ms=2000.0,
    )


def stage_thresholds() -> ConnectionCycleThresholds:
    return ConnectionCycleThresholds(
        window_size=5,
        minimum_samples=3,
        p95_warning_ms=10000.0,
        p95_critical_ms=20000.0,
        stages=ConnectionCycleStageThresholds(
            association=ConnectionStageP95Threshold(
                p95_warning_ms=1000.0,
                p95_critical_ms=2000.0,
            )
        ),
    )


def test_slo_requires_minimum_unique_measurable_cycles():
    engine = ConnectionCycleSloEngine(thresholds())

    first = engine.observe(cycle("one", 500.0))
    repeated = engine.observe(cycle("one", 500.0))
    existing = engine.observe(cycle("existing", 9999.0, session_type="observed_existing"))

    assert first.metrics.status == "insufficient_data"
    assert first.metrics.sample_count == 1
    assert first.metrics.fresh is True
    assert repeated.metrics.sample_count == 1
    assert repeated.metrics.fresh is False
    assert existing.metrics.sample_count == 1
    assert existing.metrics.fresh is False


def test_slo_warning_and_critical_use_rolling_p95():
    engine = ConnectionCycleSloEngine(thresholds())
    engine.observe(cycle("one", 500.0))
    engine.observe(cycle("two", 1000.0))
    warning = engine.observe(cycle("three", 1500.0))

    assert warning.metrics.p95_ms == 1450.0
    assert warning.metrics.status == "warning"
    assert any(item.code == "CONNECTION_CYCLE_P95_SLO" for item in warning.findings)
    assert warning.fresh_codes == {"CONNECTION_CYCLE_P95_SLO"}

    critical = engine.observe(cycle("four", 3000.0))
    assert critical.metrics.status == "critical"
    total_finding = next(
        item for item in critical.findings if item.code == "CONNECTION_CYCLE_P95_SLO"
    )
    assert total_finding.severity == "critical"
    assert total_finding.domain == "connection_cycle"


def test_stage_milestone_slo_uses_unique_time_from_connection_start():
    engine = ConnectionCycleSloEngine(stage_thresholds())

    engine.observe(cycle("one", 500.0, stages={"association": 500.0}))
    engine.observe(cycle("two", 500.0, stages={"association": 1000.0}))
    warning = engine.observe(cycle("three", 500.0, stages={"association": 1500.0}))

    association = warning.metrics.stages["association"]
    assert association.p95_ms == 1450.0
    assert association.status == "warning"
    assert warning.metrics.status == "warning"
    assert "CONNECTION_CYCLE_ASSOCIATION_P95_SLO" in warning.fresh_codes
    assert any(item.code == "CONNECTION_CYCLE_ASSOCIATION_P95_SLO" for item in warning.findings)

    repeated = engine.observe(cycle("three", 500.0, stages={"association": 1500.0}))
    assert repeated.metrics.stages["association"].sample_count == 3
    assert repeated.metrics.stages["association"].fresh is False
    assert repeated.fresh_codes == set()


def test_stage_milestone_can_be_measured_before_network_ready():
    engine = ConnectionCycleSloEngine(stage_thresholds())

    result = engine.observe(
        cycle(
            "connecting",
            None,
            state="connecting",
            stages={"association": 750.0},
        )
    )

    assert result.metrics.sample_count == 0
    assert result.metrics.stages["association"].sample_count == 1
    assert result.metrics.stages["association"].fresh is True


def test_profile_defaults_are_backward_compatible():
    profile = ProfileConfiguration.model_validate({})
    cycle_config = profile.thresholds.connection_cycle
    assert cycle_config.window_size == 20
    assert cycle_config.minimum_samples == 5
    assert cycle_config.p95_warning_ms == 8000.0
    assert cycle_config.p95_critical_ms == 15000.0
    assert cycle_config.stages.association.p95_warning_ms == 1500.0
    assert cycle_config.stages.authentication.p95_warning_ms == 3000.0
    assert cycle_config.stages.ipv4.p95_warning_ms == 5000.0
    assert cycle_config.stages.gateway.p95_warning_ms == 6000.0
    assert cycle_config.stages.dns.p95_warning_ms == 7000.0


@pytest.mark.parametrize(
    "value",
    [
        {"window_size": 4, "minimum_samples": 5},
        {"p95_warning_ms": 1000, "p95_critical_ms": 1000},
        {
            "stages": {
                "dns": {
                    "p95_warning_ms": 1000,
                    "p95_critical_ms": 1000,
                }
            }
        },
    ],
)
def test_connection_cycle_threshold_validation(value: dict[str, object]):
    with pytest.raises(ValidationError):
        ConnectionCycleThresholds.model_validate(value)
