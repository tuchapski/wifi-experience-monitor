from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample
from wifi_server.analysis.recording_v3 import analyze_recording


def _samples(metric: str, values: list[float]) -> list[MetricSample]:
    started = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)
    return [
        MetricSample(
            observed_at=started + timedelta(seconds=index),
            metric=metric,
            value=value,
        )
        for index, value in enumerate(values)
    ]


def test_v3_detects_elevated_channel_utilization() -> None:
    metrics = [
        *_samples(
            "wifi.channel_utilization_percent",
            [45, 50, 55, 65, 70, 72, 75, 78, 80, 74],
        ),
    ]

    result = analyze_recording(metrics, [])

    finding = next(
        item for item in result.findings if item["code"] == "WIFI_ELEVATED_CHANNEL_UTILIZATION"
    )
    assert finding["severity"] == "warning"
    assert result.summary["channel_utilization_percent"]["samples"] == 10
    assert result.policy["version"] == "recording-analysis-v3"


def test_v3_detects_very_high_channel_utilization() -> None:
    result = analyze_recording(
        _samples(
            "wifi.channel_utilization_percent",
            [60, 70, 80, 88, 90, 92, 94, 91, 89, 87],
        ),
        [],
    )

    assert result.summary["status"] == "critical"
    assert any(item["code"] == "WIFI_HIGH_CHANNEL_UTILIZATION" for item in result.findings)


def test_v3_correlates_retries_with_busy_channel_without_claiming_root_cause() -> None:
    metrics = [
        *_samples(
            "wifi.channel_utilization_percent",
            [72, 74, 76, 78, 80, 82, 79, 77, 75, 73],
        ),
        *_samples(
            "wifi.tx_retries_per_100_packets",
            [20, 22, 24, 26, 28, 30, 25, 23, 21, 20],
        ),
    ]

    result = analyze_recording(metrics, [])

    finding = next(
        item for item in result.findings if item["code"] == "WIFI_RETRIES_WITH_BUSY_CHANNEL"
    )
    assert finding["severity"] == "info"
    assert "distinguish" in finding["next_action"]


def test_v3_marks_survey_evidence_unavailable_for_legacy_recording() -> None:
    result = analyze_recording(
        _samples("wifi.rssi_dbm", [-60, -61, -62, -61, -60]),
        [],
    )

    assert result.summary["evidence_groups"]["rf_utilization"] is False
    assert result.summary["evidence_status"] == "partial"
    assert any("survey intervals" in limitation for limitation in result.summary["limitations"])
