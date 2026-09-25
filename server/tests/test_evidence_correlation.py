"""Evidence correlation keeps temporal context separate from causal diagnosis."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.db.recording_models import RecordingEvent
from wifi_server.services.evidence_correlation import correlate_diagnostic_evidence


def _event(observed_at: datetime, metric: str, previous: object, current: object) -> RecordingEvent:
    return RecordingEvent(
        recording_id="rec_test",
        observed_at=observed_at,
        event_type="state.changed",
        severity="info",
        data={"metric": metric, "previous": previous, "current": current},
        received_at=observed_at,
    )


def test_correlation_classifies_events_around_window_without_claiming_causality() -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    window_start = start + timedelta(seconds=60)
    window_end = start + timedelta(seconds=90)
    session.get.return_value = Mock(started_at=start, ended_at=start + timedelta(minutes=10))
    session.execute.side_effect = [
        iter([("wifi.rssi_dbm", 5, -54.0, -52.0, -50.0)]),
        iter([("wifi.rssi_dbm", 5, -73.0, -70.0, -67.0)]),
        iter([("wifi.rssi_dbm", 5, -55.0, -53.0, -51.0)]),
    ]
    session.scalars.return_value.all.return_value = [
        _event(window_start - timedelta(seconds=3), "wifi.bssid", "aa:aa", "bb:bb"),
        _event(window_start + timedelta(seconds=8), "wifi.channel", 36, 44),
        _event(window_end + timedelta(seconds=12), "wifi.bssid", "bb:bb", "cc:cc"),
    ]

    result = correlate_diagnostic_evidence(
        session,
        "rec_test",
        ["wifi.rssi_dbm"],
        window_start,
        window_end,
        30,
    )

    assert len(result.findings) == 1
    assert result.findings[0].metric == "wifi.rssi_dbm"
    assert [event.phase for event in result.events] == ["before", "during", "after"]
    assert [event.distance_seconds for event in result.events] == [3.0, 0.0, 12.0]
    assert [event.seconds_from_window_start for event in result.events] == [-3.0, 8.0, 42.0]
    assert result.events[0].data["metric"] == "wifi.bssid"
    assert not hasattr(result.events[0], "confidence")
    assert not hasattr(result.events[0], "cause")


def test_correlation_uses_recording_bounds_for_context_query() -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    end = start + timedelta(seconds=45)
    session.get.return_value = Mock(started_at=start, ended_at=end)
    session.execute.side_effect = [iter([]), iter([]), iter([])]
    session.scalars.return_value.all.return_value = []

    result = correlate_diagnostic_evidence(
        session,
        "rec_test",
        ["wifi.rssi_dbm"],
        start + timedelta(seconds=5),
        start + timedelta(seconds=40),
        30,
    )

    assert result.findings == []
    assert result.events == []
    statement = session.scalars.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "recording_events.event_type = 'state.changed'" in compiled
    assert "recording_events.observed_at" in compiled
