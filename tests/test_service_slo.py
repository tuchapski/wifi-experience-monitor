from wem.analysis.service_slo import ServiceSloEngine
from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    NetworkMetrics,
    SensorHealthMetrics,
    SensorSnapshot,
    WifiMetrics,
)
from wem.models.metrics import (
    TestOutcome as Outcome,
)
from wem.profiles.models import (
    ServiceSloTarget,
    ServiceSloThresholds,
)
from wem.profiles.models import (
    TestConfigurations as Configurations,
)
from wem.profiles.models import (
    TestProfileConfig as ProfileConfiguration,
)


def target(
    latency_warning: float,
    latency_critical: float,
    *,
    packet_warning: float | None = None,
    packet_critical: float | None = None,
) -> ServiceSloTarget:
    return ServiceSloTarget(
        availability_warning_percent=99.0,
        availability_critical_percent=90.0,
        latency_p95_warning_ms=latency_warning,
        latency_p95_critical_ms=latency_critical,
        packet_loss_p95_warning_percent=packet_warning,
        packet_loss_p95_critical_percent=packet_critical,
    )


def thresholds() -> ServiceSloThresholds:
    return ServiceSloThresholds(
        window_size=10,
        minimum_samples=5,
        gateway=target(200.0, 1000.0, packet_warning=10.0, packet_critical=50.0),
        internet=target(300.0, 1000.0, packet_warning=10.0, packet_critical=50.0),
        dns=target(300.0, 1000.0),
        https=target(1200.0, 3000.0),
    )


def snapshot(
    *,
    service: str,
    status: str,
    fresh: bool = True,
    latency_ms: float | None = None,
    packet_loss_percent: float | None = None,
) -> SensorSnapshot:
    connectivity = ConnectivityMetrics(
        tests={service: Outcome(status=status, reason="fixture", fresh=fresh)}
    )
    if service == "gateway":
        connectivity.gateway_latency_avg_ms = latency_ms
        connectivity.gateway_packet_loss_percent = packet_loss_percent
    elif service == "internet":
        connectivity.internet_latency_avg_ms = latency_ms
        connectivity.internet_packet_loss_percent = packet_loss_percent
    elif service == "dns":
        connectivity.dns_latency_ms = latency_ms
    elif service == "https":
        connectivity.https_total_time_ms = latency_ms

    return SensorSnapshot.create(
        health=SensorHealthMetrics("wlan0"),
        calibration=CalibrationResult("ok", True),
        wifi=WifiMetrics("wlan0", ssid="CORP"),
        network=NetworkMetrics("wlan0"),
        connectivity=connectivity,
    )


def test_service_slo_uses_only_fresh_definitive_executions():
    engine = ServiceSloEngine(thresholds(), Configurations())

    for _ in range(5):
        result = engine.evaluate(
            snapshot(
                service="gateway",
                status="passed",
                latency_ms=50.0,
                packet_loss_percent=0.0,
            )
        )

    gateway = result.metrics.services["gateway"]
    assert gateway.status == "healthy"
    assert gateway.measurable_count == 5
    assert gateway.availability_percent == 100.0
    assert "SERVICE_SLO_GATEWAY" in result.fresh_codes

    cached = engine.evaluate(
        snapshot(
            service="gateway",
            status="passed",
            fresh=False,
            latency_ms=9999.0,
            packet_loss_percent=100.0,
        )
    )
    assert cached.metrics.services["gateway"].measurable_count == 5
    assert "SERVICE_SLO_GATEWAY" not in cached.fresh_codes


def test_service_slo_detects_latency_and_availability_violations():
    latency_engine = ServiceSloEngine(thresholds(), Configurations())
    for value in (100.0, 100.0, 100.0, 100.0, 500.0):
        latency_result = latency_engine.evaluate(
            snapshot(
                service="gateway",
                status="passed",
                latency_ms=value,
                packet_loss_percent=0.0,
            )
        )

    gateway = latency_result.metrics.services["gateway"]
    assert gateway.latency_p95_ms == 420.0
    assert gateway.status == "warning"
    assert latency_result.findings[0].code == "SERVICE_SLO_GATEWAY"

    availability_engine = ServiceSloEngine(thresholds(), Configurations())
    for status in ("passed", "passed", "passed", "passed", "failed"):
        availability_result = availability_engine.evaluate(
            snapshot(
                service="dns",
                status=status,
                latency_ms=50.0 if status == "passed" else None,
            )
        )

    dns = availability_result.metrics.services["dns"]
    assert dns.availability_percent == 80.0
    assert dns.status == "critical"
    assert availability_result.findings[0].severity == "critical"


def test_measurement_error_is_not_service_unavailability():
    engine = ServiceSloEngine(thresholds(), Configurations())

    for _ in range(5):
        engine.evaluate(snapshot(service="https", status="passed", latency_ms=100.0))
    result = engine.evaluate(snapshot(service="https", status="error"))

    https = result.metrics.services["https"]
    assert https.measurable_count == 5
    assert https.success_count == 5
    assert https.measurement_error_count == 1
    assert https.availability_percent == 100.0
    assert "SERVICE_SLO_HTTPS" not in result.fresh_codes


def test_service_slo_profile_defaults_are_backward_compatible():
    profile = ProfileConfiguration.model_validate({})
    slo = profile.thresholds.service_slo

    assert slo.enabled is True
    assert slo.window_size == 60
    assert slo.minimum_samples == 20
    assert slo.gateway.latency_p95_warning_ms == 50.0
    assert slo.internet.latency_p95_warning_ms == 150.0
    assert slo.dns.latency_p95_warning_ms == 250.0
    assert slo.https.latency_p95_warning_ms == 1000.0
