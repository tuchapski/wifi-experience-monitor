from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample, StateEvent
from wifi_server.analysis.recording_v5 import analyze_recording

START = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)


def sample(metric: str, value: float, seconds: int) -> MetricSample:
    return MetricSample(START + timedelta(seconds=seconds), metric, value)


def change(metric: str, seconds: int, previous: object, current: object) -> StateEvent:
    return StateEvent(
        START + timedelta(seconds=seconds),
        "state.changed",
        {"metric": metric, "previous": previous, "current": current},
    )


def test_v5_compares_medians_around_bssid_transition() -> None:
    metrics = [
        *(
            sample("wifi.rssi_dbm", value, second)
            for second, value in ((15, -77), (16, -76), (17, -75), (21, -65), (22, -64), (23, -63))
        ),
        *(
            sample("wifi.tx_retries_per_100_packets", value, second)
            for second, value in ((15, 30), (16, 25), (17, 20), (21, 9), (22, 7), (23, 5))
        ),
    ]

    result = analyze_recording(metrics, [change("wifi.bssid", 20, "old", "new")])

    transition = result.summary["bssid_transitions"][0]
    assert result.policy["version"] == "recording-analysis-v5"
    assert transition["status"] == "comparable"
    assert transition["metrics"]["wifi.rssi_dbm"]["delta"] == 12
    assert transition["metrics"]["wifi.tx_retries_per_100_packets"]["delta"] == -18
    assert transition["metrics"]["wifi.channel_utilization_percent"]["delta"] is None
    assert not any(finding["code"] == "WIFI_ROAM_CAUSE" for finding in result.findings)


def test_v5_marks_missing_or_distant_samples_as_limited() -> None:
    metrics = [
        sample("wifi.rssi_dbm", -70, 11),
        sample("wifi.rssi_dbm", -70, 12),
        sample("wifi.rssi_dbm", -70, 13),
        sample("wifi.rssi_dbm", -60, 24),
        sample("wifi.rssi_dbm", -60, 25),
        sample("wifi.rssi_dbm", -60, 26),
    ]

    result = analyze_recording(metrics, [change("wifi.bssid", 20, "old", "new")])

    transition = result.summary["bssid_transitions"][0]
    assert transition["status"] == "limited"
    assert transition["metrics"]["wifi.rssi_dbm"]["before_samples"] == 3
    assert transition["metrics"]["wifi.rssi_dbm"]["delta"] is None


def test_v5_discloses_overlapping_changes_and_skips_disconnect_to_bssid() -> None:
    events = [
        change("wifi.bssid", 20, "old", "new"),
        change("wifi.connected", 21, True, False),
        change("wifi.bssid", 30, "new", None),
    ]
    metrics = [
        *(sample("wifi.rssi_dbm", -70, second) for second in (17, 18, 19)),
        *(sample("wifi.rssi_dbm", -60, second) for second in (21, 22, 23)),
    ]

    result = analyze_recording(metrics, events)

    assert len(result.summary["bssid_transitions"]) == 1
    transition = result.summary["bssid_transitions"][0]
    assert transition["status"] == "limited"
    assert transition["metrics"]["wifi.rssi_dbm"]["delta"] == 10
    assert "connectivity change" in transition["limitations"][0]


def test_v5_keeps_v4_degraded_windows() -> None:
    metrics = [
        sample(metric, value, second)
        for second in (0, 1, 2)
        for metric, value in (
            ("wifi.rssi_dbm", -80),
            ("wifi.tx_retries_per_100_packets", 30),
        )
    ]

    result = analyze_recording(metrics, [])

    assert len(result.summary["degraded_windows"]) == 1
    assert result.summary["bssid_transitions"] == []
