from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample, StateEvent, analyze_recording


def _sample(
    metric: str,
    value: float,
    second: int,
) -> MetricSample:
    return MetricSample(
        observed_at=datetime(2026, 9, 23, 22, 0, tzinfo=UTC) + timedelta(seconds=second),
        metric=metric,
        value=value,
    )


def test_analysis_detects_sustained_low_signal() -> None:
    metrics = [
        _sample("wifi.rssi_dbm", value, index)
        for index, value in enumerate([-78, -79, -80, -81, -80, -79])
    ]

    result = analyze_recording(metrics, [])

    assert result.summary["status"] == "warning"
    assert result.summary["rssi"]["samples"] == 6
    assert len(result.summary["low_signal_windows"]) == 1
    assert any(finding["code"] == "WIFI_LOW_SIGNAL" for finding in result.findings)


def test_analysis_prioritizes_very_low_signal() -> None:
    metrics = [
        _sample("wifi.rssi_dbm", value, index)
        for index, value in enumerate([-84, -85, -86, -84, -83])
    ]

    result = analyze_recording(metrics, [])

    assert result.summary["status"] == "critical"
    codes = {finding["code"] for finding in result.findings}
    assert "WIFI_VERY_LOW_SIGNAL" in codes
    assert "WIFI_LOW_SIGNAL" not in codes


def test_analysis_reports_state_changes_without_calling_them_root_cause() -> None:
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    events = [
        StateEvent(
            observed_at=started,
            event_type="state.changed",
            data={
                "metric": "wifi.bssid",
                "previous": "aa:aa:aa:aa:aa:aa",
                "current": "bb:bb:bb:bb:bb:bb",
            },
        ),
        StateEvent(
            observed_at=started + timedelta(seconds=1),
            event_type="state.changed",
            data={"metric": "wifi.channel", "previous": 36, "current": 44},
        ),
    ]

    result = analyze_recording([], events)

    assert result.summary["status"] == "observed"
    assert result.summary["state_changes"]["bssid"] == 1
    assert result.summary["state_changes"]["channel"] == 1
    codes = {finding["code"] for finding in result.findings}
    assert codes == {"WIFI_BSSID_CHANGED", "WIFI_CHANNEL_CHANGED"}


def test_analysis_detects_link_rate_variation() -> None:
    metrics = [
        _sample("wifi.tx_rate_mbps", value, index)
        for index, value in enumerate([480, 480, 480, 480, 480, 480, 480, 480, 120, 120])
    ]

    result = analyze_recording(metrics, [])

    finding = next(item for item in result.findings if item["code"] == "WIFI_TX_VARIATION")
    assert finding["severity"] == "warning"
    assert result.summary["tx_rate_mbps"]["p50"] == 480
