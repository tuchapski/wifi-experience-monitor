from concurrent.futures import Future
from datetime import UTC, datetime, timedelta

import pytest
from wifi_agent.config import AgentSettings
from wifi_agent.core.rf import BssObservation, RfScanResult
from wifi_agent.runtime.rf_scan import RfScanRuntime


def _bss() -> BssObservation:
    return BssObservation(
        bssid="98:7e:ca:8a:3e:0e",
        interface="wlp0s20f3",
        ssid="AeP",
        frequency_mhz=5805,
        channel=161,
        band="5ghz",
        rssi_dbm=-61.0,
        associated=True,
    )


def _result(
    observed_at: datetime,
    *,
    error: str | None = None,
) -> RfScanResult:
    return RfScanResult(
        interface="wlp0s20f3",
        observed_at=observed_at,
        duration_ms=125.4,
        bsses=() if error else (_bss(),),
        error=error,
    )


def _values(runtime: RfScanRuntime, now: datetime) -> dict[str, object]:
    return {item.metric: item.value for item in runtime.readiness_observations(now)}


def test_runtime_refuses_overlapping_scans_and_enforces_cadence() -> None:
    runtime = RfScanRuntime(
        "wlp0s20f3",
        interval_seconds=60,
        timeout_seconds=15,
    )
    pending: Future[RfScanResult] = Future()
    runtime._executor.submit = lambda *args, **kwargs: pending  # type: ignore[method-assign]

    try:
        assert runtime.maybe_start(100.0) is True
        assert runtime.running is True
        assert runtime.maybe_start(101.0) is False

        pending.set_result(_result(datetime(2026, 9, 29, 12, 0, tzinfo=UTC)))
        assert runtime.poll() is pending.result()
        assert runtime.running is False
        assert runtime.maybe_start(159.9) is False
    finally:
        runtime.close()


def test_successful_scan_becomes_verified_runtime_evidence() -> None:
    runtime = RfScanRuntime("wlp0s20f3", interval_seconds=60, timeout_seconds=15)
    observed_at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    runtime._latest = _result(observed_at)

    try:
        values = _values(runtime, observed_at + timedelta(seconds=5))
    finally:
        runtime.close()

    assert values["wifi.scan_status"] == "verified"
    assert values["wifi.scan_bss_count"] == 1
    assert values["wifi.scan_associated_seen"] is True
    assert values["wifi.scan_duration_ms"] == 125.4
    assert values["wifi.scan_last_completed_at"] == observed_at.isoformat()
    assert "1 BSS" in str(values["wifi.scan_reason"])


def test_failed_scan_is_unavailable_runtime_evidence() -> None:
    runtime = RfScanRuntime("wlp0s20f3", interval_seconds=60, timeout_seconds=15)
    observed_at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    runtime._latest = _result(
        observed_at,
        error="iw scan failed: Operation not permitted",
    )

    try:
        values = _values(runtime, observed_at + timedelta(seconds=5))
    finally:
        runtime.close()

    assert values["wifi.scan_status"] == "unavailable"
    assert values["wifi.scan_bss_count"] == 0
    assert values["wifi.scan_reason"] == "iw scan failed: Operation not permitted"


def test_successful_scan_becomes_degraded_when_stale() -> None:
    runtime = RfScanRuntime("wlp0s20f3", interval_seconds=60, timeout_seconds=15)
    observed_at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    runtime._latest = _result(observed_at)

    try:
        values = _values(runtime, observed_at + timedelta(seconds=181))
    finally:
        runtime.close()

    assert values["wifi.scan_status"] == "degraded"
    assert "stale" in str(values["wifi.scan_reason"]).lower()


def test_pending_readiness_does_not_claim_scan_is_verified() -> None:
    runtime = RfScanRuntime("wlp0s20f3", interval_seconds=60, timeout_seconds=15)

    try:
        values = _values(runtime, datetime(2026, 9, 29, 12, 0, tzinfo=UTC))
    finally:
        runtime.close()

    assert values["wifi.scan_status"] == "pending"
    assert values["wifi.scan_running"] is False


def test_rf_scan_settings_have_conservative_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEM_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WEM_AGENT_RF_SCAN_ENABLED", raising=False)
    monkeypatch.delenv("WEM_AGENT_RF_SCAN_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("WEM_AGENT_RF_SCAN_TIMEOUT_SECONDS", raising=False)

    settings = AgentSettings.from_environment()

    assert settings.rf_scan_enabled is True
    assert settings.rf_scan_interval_seconds == 60
    assert settings.rf_scan_timeout_seconds == 15


@pytest.mark.parametrize("value", ["0", "false", "no", "off"])
def test_rf_scan_can_be_disabled_from_environment(
    monkeypatch,
    tmp_path,
    value: str,
) -> None:
    monkeypatch.setenv("WEM_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEM_AGENT_RF_SCAN_ENABLED", value)

    assert AgentSettings.from_environment().rf_scan_enabled is False


def test_invalid_rf_scan_boolean_is_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEM_AGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEM_AGENT_RF_SCAN_ENABLED", "sometimes")

    with pytest.raises(ValueError, match="WEM_AGENT_RF_SCAN_ENABLED"):
        AgentSettings.from_environment()
