from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample
from wifi_server.analysis.recording_v2 import analyze_recording


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


def test_v2_detects_elevated_retries_from_interval_metrics() -> None:
    metrics = [
        *_samples("wifi.rssi_dbm", [-60, -61, -62, -61, -60]),
        *_samples(
            "wifi.tx_retries_per_100_packets",
            [10, 12, 22, 24, 28, 30, 25, 20, 18, 15],
        ),
        *_samples("wifi.tx_failed_percent", [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ]

    result = analyze_recording(metrics, [])

    finding = next(item for item in result.findings if item["code"] == "WIFI_ELEVATED_RETRIES")
    assert finding["severity"] == "warning"
    assert result.summary["tx_retries_per_100_packets"]["samples"] == 10
    assert result.policy["version"] == "recording-analysis-v2"


def test_v2_detects_tx_failures() -> None:
    metrics = [
        *_samples("wifi.tx_retries_per_100_packets", [5, 5, 5, 5, 5]),
        *_samples("wifi.tx_failed_percent", [0, 1, 2, 7, 8]),
    ]

    result = analyze_recording(metrics, [])

    assert result.summary["status"] == "critical"
    assert any(item["code"] == "WIFI_TX_FAILURES" for item in result.findings)


def test_v2_marks_counter_evidence_unavailable_for_legacy_recording() -> None:
    result = analyze_recording(
        _samples("wifi.rssi_dbm", [-60, -61, -62, -61, -60]),
        [],
    )

    assert result.summary["evidence_groups"]["counter_quality"] is False
    assert result.summary["evidence_status"] == "partial"
    assert any("counter intervals" in limitation for limitation in result.summary["limitations"])
