import pytest
from pydantic import ValidationError

from wem.analysis.connection_cycle_slo import ConnectionCycleSloEngine
from wem.models.metrics import ConnectionCycleMetrics
from wem.profiles.models import ConnectionCycleThresholds, TestProfileConfig


def cycle(session_id: str, duration_ms: float | None, *, session_type: str = "reconnect"):
    return ConnectionCycleMetrics(
        session_id=session_id,
        session_type=session_type,
        state="ready",
        ssid="CORP",
        bssid="aa:bb:cc:dd:ee:ff",
        started_at="2026-09-22T12:00:00+00:00",
        last_observed_at="2026-09-22T12:00:05+00:00",
        completed_at=None,
        total_time_ms=duration_ms,
        sample_resolution_ms=5000.0,
    )


def thresholds() -> ConnectionCycleThresholds:
    return ConnectionCycleThresholds(
        window_size=5,
        minimum_samples=3,
        p95_warning_ms=1000.0,
        p95_critical_ms=2000.0,
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
    assert warning.finding is not None
    assert warning.finding.code == "CONNECTION_CYCLE_P95_SLO"
    assert warning.finding.domain == "connection_cycle"

    critical = engine.observe(cycle("four", 3000.0))
    assert critical.metrics.status == "critical"
    assert critical.finding is not None
    assert critical.finding.severity == "critical"


def test_profile_defaults_are_backward_compatible():
    profile = TestProfileConfig.model_validate({})
    assert profile.thresholds.connection_cycle.window_size == 20
    assert profile.thresholds.connection_cycle.minimum_samples == 5
    assert profile.thresholds.connection_cycle.p95_warning_ms == 8000.0
    assert profile.thresholds.connection_cycle.p95_critical_ms == 15000.0


@pytest.mark.parametrize(
    "value",
    [
        {"window_size": 4, "minimum_samples": 5},
        {"p95_warning_ms": 1000, "p95_critical_ms": 1000},
    ],
)
def test_connection_cycle_threshold_validation(value: dict[str, object]):
    with pytest.raises(ValidationError):
        ConnectionCycleThresholds.model_validate(value)
