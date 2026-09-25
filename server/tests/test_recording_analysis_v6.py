from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample, StateEvent
from wifi_server.analysis.recording_v6 import analyze_recording

START = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)


def cycle(seconds: int, interval: float = 1, errors: int = 0) -> MetricSample:
    return MetricSample(
        START + timedelta(seconds=seconds),
        "sensor.collection_cycle",
        1.0,
        {"configured_interval_seconds": interval, "collector_errors_count": errors},
    )


def analyze(metrics: list[MetricSample], seconds: int = 10):
    return analyze_recording(
        metrics, [], started_at=START, ended_at=START + timedelta(seconds=seconds)
    )


def test_continuous_cycles_preserve_existing_wifi_findings() -> None:
    metrics = [cycle(second) for second in range(1, 10)]
    metrics.extend(
        MetricSample(START + timedelta(seconds=second), "wifi.rssi_dbm", -85)
        for second in range(1, 7)
    )
    result = analyze(metrics)
    assert result.policy["version"] == "recording-analysis-v6"
    assert result.summary["collection_integrity"]["status"] == "continuous"
    assert result.summary["collection_integrity"]["gaps"] == []
    assert any(finding["code"] == "WIFI_VERY_LOW_SIGNAL" for finding in result.findings)
    assert result.summary["status"] == "critical"


def test_cycle_markers_alone_are_not_wifi_evidence() -> None:
    result = analyze([cycle(second) for second in range(1, 10)])
    assert result.summary["collection_integrity"]["status"] == "continuous"
    assert result.summary["status"] == "limited"


def test_paused_collection_has_gap_and_partial_evidence() -> None:
    result = analyze([cycle(second) for second in (1, 2, 8, 9)])
    continuity = result.summary["collection_integrity"]
    assert continuity["status"] == "interrupted"
    assert continuity["gap_threshold_seconds"] == 3
    assert continuity["gaps"] == [
        {
            "started_at": (START + timedelta(seconds=2)).isoformat(),
            "ended_at": (START + timedelta(seconds=8)).isoformat(),
            "duration_seconds": 6.0,
        }
    ]
    assert result.summary["evidence_status"] == "partial"


def test_start_and_end_boundaries_are_checked() -> None:
    result = analyze([cycle(5)], seconds=12)
    assert len(result.summary["collection_integrity"]["gaps"]) == 2


def test_old_recording_without_markers_does_not_claim_continuity() -> None:
    metrics = [MetricSample(START, "wifi.rssi_dbm", -55)]
    result = analyze(metrics)
    assert result.summary["collection_integrity"]["status"] == "unavailable"
    assert result.summary["status"] == "limited"
    assert result.summary["evidence_status"] == "partial"


def test_malformed_cadence_and_collector_errors_are_visible() -> None:
    assert (
        analyze([cycle(1, interval=0)]).summary["collection_integrity"]["status"] == "unavailable"
    )
    assert (
        analyze([cycle(1), cycle(2, interval=2)]).summary["collection_integrity"]["status"]
        == "unavailable"
    )
    result = analyze([cycle(second, errors=1 if second == 2 else 0) for second in range(1, 10)])
    assert result.summary["collection_integrity"]["status"] == "impaired"
    assert result.summary["collection_integrity"]["collector_error_cycles"] == 1


def test_disconnection_finding_keeps_critical_severity_when_collection_pauses() -> None:
    event = StateEvent(
        START + timedelta(seconds=2),
        "state.changed",
        {"metric": "wifi.connected", "previous": True, "current": False},
    )
    result = analyze_recording(
        [cycle(1), cycle(9)],
        [event],
        started_at=START,
        ended_at=START + timedelta(seconds=10),
    )
    assert result.summary["status"] == "critical"
    assert result.summary["collection_integrity"]["status"] == "interrupted"
