"""Before/during/after comparisons use raw metric aggregates and preserve missing data."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.services.diagnostic_windows import compare_diagnostic_window


def test_comparison_preserves_missing_periods_as_missing_not_zero() -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    session.get.return_value = Mock(started_at=start, ended_at=start + timedelta(minutes=10))
    session.execute.side_effect = [
        iter([]),
        iter([("wifi.rssi_dbm", 3, -75.0, -70.0, -65.0)]),
        iter([("wifi.rssi_dbm", 2, -56.0, -55.0, -54.0)]),
    ]

    result = compare_diagnostic_window(
        session,
        "rec_test",
        ["wifi.rssi_dbm"],
        start + timedelta(seconds=10),
        start + timedelta(seconds=20),
        30,
    )

    metric = result.metrics[0]
    assert result.before_start == start
    assert metric.before.sample_count == 0
    assert metric.before.average is None
    assert metric.during.sample_count == 3
    assert metric.during.average == -70.0
    assert metric.after.average == -55.0


def test_comparison_clamps_after_period_to_completed_recording() -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    end = start + timedelta(seconds=45)
    session.get.return_value = Mock(started_at=start, ended_at=end)
    session.execute.side_effect = [iter([]), iter([]), iter([])]

    result = compare_diagnostic_window(
        session,
        "rec_test",
        ["network.gateway_latency_ms"],
        start + timedelta(seconds=30),
        start + timedelta(seconds=40),
        30,
    )

    assert result.after_end == end
    assert result.metrics[0].after.sample_count == 0
    assert result.metrics[0].after.minimum is None
