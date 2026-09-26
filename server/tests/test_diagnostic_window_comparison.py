"""Before/during/after comparisons use raw metric aggregates and preserve missing data."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
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


def test_findings_detect_meaningful_deterioration_and_recovery() -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    session.get.return_value = Mock(started_at=start, ended_at=start + timedelta(minutes=10))
    session.execute.side_effect = [
        iter([("wifi.rssi_dbm", 5, -54.0, -52.0, -50.0)]),
        iter([("wifi.rssi_dbm", 5, -73.0, -70.0, -67.0)]),
        iter([("wifi.rssi_dbm", 5, -55.0, -53.0, -51.0)]),
    ]

    result = compare_diagnostic_window(
        session,
        "rec_test",
        ["wifi.rssi_dbm"],
        start + timedelta(seconds=60),
        start + timedelta(seconds=90),
        30,
    )

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.metric == "wifi.rssi_dbm"
    assert finding.direction == "decreased"
    assert finding.baseline == -52.0
    assert finding.during == -70.0
    assert finding.delta == -18.0
    assert finding.after == -53.0
    assert finding.recovery == "recovered"


def test_findings_ignore_noise_and_preserve_unknown_recovery() -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    session.get.return_value = Mock(started_at=start, ended_at=None)
    session.execute.side_effect = [
        iter(
            [
                ("wifi.rssi_dbm", 5, -55.0, -52.0, -50.0),
                ("wifi.tx_retries_per_100_packets", 5, 1.0, 2.0, 3.0),
            ]
        ),
        iter(
            [
                ("wifi.rssi_dbm", 5, -57.0, -55.0, -53.0),
                ("wifi.tx_retries_per_100_packets", 5, 8.0, 10.0, 12.0),
            ]
        ),
        iter([]),
    ]

    result = compare_diagnostic_window(
        session,
        "rec_test",
        ["wifi.rssi_dbm", "wifi.tx_retries_per_100_packets"],
        start + timedelta(seconds=60),
        start + timedelta(seconds=90),
        30,
    )

    assert [finding.metric for finding in result.findings] == ["wifi.tx_retries_per_100_packets"]
    assert result.findings[0].direction == "increased"
    assert result.findings[0].delta == 8.0
    assert result.findings[0].recovery == "unknown"


@pytest.mark.parametrize(
    ("metric", "baseline", "during", "after", "expected_delta"),
    [
        ("wifi.tx_retries_per_100_packets", 2.0, 10.0, 3.0, 8.0),
        ("wifi.tx_failed_percent", 0.5, 3.0, 1.0, 2.5),
        ("wifi.channel_utilization_percent", 30.0, 55.0, 35.0, 25.0),
        ("wifi.channel_rx_percent", 10.0, 35.0, 15.0, 25.0),
        ("wifi.channel_tx_percent", 10.0, 35.0, 15.0, 25.0),
    ],
)
def test_findings_use_canonical_recorded_metric_names(
    metric: str,
    baseline: float,
    during: float,
    after: float,
    expected_delta: float,
) -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    session.get.return_value = Mock(started_at=start, ended_at=start + timedelta(minutes=10))
    session.execute.side_effect = [
        iter([(metric, 5, baseline, baseline, baseline)]),
        iter([(metric, 5, during, during, during)]),
        iter([(metric, 5, after, after, after)]),
    ]

    result = compare_diagnostic_window(
        session,
        "rec_test",
        [metric],
        start + timedelta(seconds=60),
        start + timedelta(seconds=90),
        30,
    )

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.metric == metric
    assert finding.direction == "increased"
    assert finding.delta == expected_delta
    assert finding.recovery == "recovered"
