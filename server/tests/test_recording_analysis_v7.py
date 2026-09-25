from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample, StateEvent
from wifi_server.analysis.recording_v7 import analyze_recording

START = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def cycle(second: int, errors: int = 0) -> MetricSample:
    return MetricSample(
        START + timedelta(seconds=second),
        "sensor.collection_cycle",
        1.0,
        {"configured_interval_seconds": 1, "collector_errors_count": errors},
    )


def wifi(second: int, current: bool, previous: bool | None, initial: bool = False) -> StateEvent:
    return StateEvent(
        START + timedelta(seconds=second),
        "state.initial" if initial else "state.changed",
        {"metric": "wifi.connected", "previous": previous, "current": current},
    )


def analyze(metrics: list[MetricSample], events: list[StateEvent], end: int = 10):
    return analyze_recording(
        metrics,
        events,
        started_at=START,
        ended_at=START + timedelta(seconds=end),
    )


def test_bounded_outage_keeps_disconnection_finding() -> None:
    result = analyze(
        [cycle(second) for second in range(1, 10)],
        [wifi(5, True, False), wifi(2, False, True)],
    )
    interval = result.summary["disconnection_intervals"][0]
    assert result.policy["version"] == "recording-analysis-v7"
    assert interval["status"] == "bounded"
    assert interval["duration_seconds"] == 3
    assert result.summary["disconnection_summary"] == {
        "total": 1,
        "bounded": 1,
        "limited": 0,
        "open": 0,
    }
    assert any(finding["code"] == "WIFI_DISCONNECTED" for finding in result.findings)
    assert result.summary["status"] == "critical"


def test_gap_inside_outage_removes_measured_duration() -> None:
    result = analyze(
        [cycle(second) for second in (1, 2, 7, 8, 9)],
        [wifi(2, False, True), wifi(7, True, False)],
    )
    interval = result.summary["disconnection_intervals"][0]
    assert result.summary["collection_integrity"]["status"] == "interrupted"
    assert interval["status"] == "limited"
    assert interval["duration_seconds"] is None
    assert any("Collection paused" in reason for reason in interval["limitations"])


def test_gap_outside_outage_does_not_invalidate_its_duration() -> None:
    result = analyze(
        [cycle(second) for second in (1, 2, 3, 4, 5, 12)],
        [wifi(2, False, True), wifi(5, True, False)],
        end=13,
    )
    assert result.summary["collection_integrity"]["status"] == "interrupted"
    assert result.summary["disconnection_intervals"][0]["duration_seconds"] == 3


def test_gap_ending_at_disconnect_limits_unknown_start_time() -> None:
    result = analyze(
        [cycle(second) for second in (1, 5, 6, 7, 8, 9)],
        [wifi(5, False, True), wifi(6, True, False)],
    )
    assert result.summary["disconnection_intervals"][0]["status"] == "limited"
    assert result.summary["disconnection_intervals"][0]["duration_seconds"] is None


def test_initially_disconnected_and_open_outage_have_no_duration() -> None:
    result = analyze(
        [cycle(second) for second in range(1, 10)],
        [wifi(1, False, None, initial=True), wifi(3, True, False), wifi(8, False, True)],
    )
    intervals = result.summary["disconnection_intervals"]
    assert [item["status"] for item in intervals] == ["limited", "open"]
    assert all(item["duration_seconds"] is None for item in intervals)
    assert intervals[1]["reconnected_at"] is None
    assert result.summary["disconnection_summary"]["open"] == 1


def test_initial_connected_state_after_restart_is_not_a_measured_recovery() -> None:
    result = analyze(
        [cycle(second) for second in range(1, 10)],
        [wifi(2, False, True), wifi(5, True, None, initial=True)],
    )
    interval = result.summary["disconnection_intervals"][0]
    assert interval["status"] == "limited"
    assert interval["duration_seconds"] is None


def test_collector_errors_inside_outage_limit_only_that_interval() -> None:
    result = analyze(
        [cycle(second, errors=1 if second == 3 else 0) for second in range(1, 10)],
        [wifi(2, False, True), wifi(5, True, False), wifi(7, False, True), wifi(9, True, False)],
    )
    intervals = result.summary["disconnection_intervals"]
    assert intervals[0]["status"] == "limited"
    assert intervals[1]["status"] == "bounded"


def test_legacy_recording_without_cycle_markers_cannot_bound_outage() -> None:
    result = analyze([], [wifi(2, False, True), wifi(5, True, False)])
    assert result.summary["disconnection_intervals"][0]["duration_seconds"] is None
    assert result.summary["disconnection_intervals"][0]["status"] == "limited"
