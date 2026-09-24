from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample
from wifi_server.analysis.recording_v4 import analyze_recording

STARTED = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)


def _sample(metric: str, value: float, second: int) -> MetricSample:
    return MetricSample(
        observed_at=STARTED + timedelta(seconds=second),
        metric=metric,
        value=value,
    )


def _series(metric: str, values: list[float], start: int = 0) -> list[MetricSample]:
    return [_sample(metric, value, start + index) for index, value in enumerate(values)]


def test_v4_builds_correlated_degraded_window() -> None:
    metrics = [
        *_series("wifi.rssi_dbm", [-78, -79, -80, -78]),
        *_series("wifi.tx_retries_per_100_packets", [25, 30, 28, 24]),
        *_series("wifi.channel_utilization_percent", [74, 78, 80, 76]),
    ]

    result = analyze_recording(metrics, [])

    assert result.policy["version"] == "recording-analysis-v4"
    assert len(result.summary["degraded_windows"]) == 1
    window = result.summary["degraded_windows"][0]
    assert window["sample_count"] == 4
    assert window["duration_seconds"] == 3
    assert window["domains"] == ["airtime", "reliability", "signal"]
    assert window["minimum_rssi_dbm"] == -80
    assert window["maximum_retries_per_100_packets"] == 30
    assert window["maximum_channel_utilization_percent"] == 80
    assert any(finding["code"] == "WIFI_CORRELATED_DEGRADATION" for finding in result.findings)


def test_v4_ignores_isolated_correlated_spike() -> None:
    metrics = [
        *_series("wifi.rssi_dbm", [-60, -60, -78, -60, -60]),
        *_series(
            "wifi.tx_retries_per_100_packets",
            [5, 5, 30, 5, 5],
        ),
        *_series(
            "wifi.channel_utilization_percent",
            [20, 20, 75, 20, 20],
        ),
    ]

    result = analyze_recording(metrics, [])

    assert result.summary["degraded_windows"] == []
    assert not any(finding["code"] == "WIFI_CORRELATED_DEGRADATION" for finding in result.findings)


def test_v4_separates_windows_after_sampling_gap() -> None:
    metrics: list[MetricSample] = []
    for second in (0, 1, 2, 10, 11, 12):
        metrics.extend(
            [
                _sample("wifi.rssi_dbm", -79, second),
                _sample("wifi.tx_retries_per_100_packets", 28, second),
                _sample("wifi.channel_utilization_percent", 76, second),
            ]
        )

    result = analyze_recording(metrics, [])

    assert len(result.summary["degraded_windows"]) == 2
    assert result.summary["degraded_windows"][0]["duration_seconds"] == 2
    assert result.summary["degraded_windows"][1]["duration_seconds"] == 2


def test_v4_marks_correlation_evidence_partial_without_overlap() -> None:
    metrics = [
        *_series("wifi.rssi_dbm", [-60, -61, -62, -61, -60]),
        *_series(
            "wifi.channel_utilization_percent",
            [20, 25, 30, 35, 40],
            start=20,
        ),
    ]

    result = analyze_recording(metrics, [])

    assert result.summary["evidence_groups"]["temporal_correlation"] is False
    assert result.summary["evidence_status"] == "partial"
    assert any("temporal correlation" in limitation for limitation in result.summary["limitations"])
