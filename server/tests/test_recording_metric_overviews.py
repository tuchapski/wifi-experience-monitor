"""Long recordings retain short peaks and full-window statistics in bounded charts."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.services.metric_overviews import get_metric_overviews, summarize_metric_rows


def test_long_capture_keeps_early_and_late_extremes() -> None:
    start = datetime(2026, 9, 25, tzinfo=UTC)
    values = [-60.0] * 1200
    values[23] = -92.0
    values[723] = -35.0
    values[-1] = -61.0
    rows = (
        ("wifi.rssi_dbm", start + timedelta(seconds=index), value, index + 1)
        for index, value in enumerate(values)
    )

    results = summarize_metric_rows(
        rows, ["wifi.rssi_dbm", "wifi.snr_db"], start, start + timedelta(seconds=1200), 20
    )

    signal, missing = results
    assert signal.sample_count == 1200
    assert (signal.minimum, signal.maximum) == (-92, -35)
    assert signal.average == sum(values) / len(values)
    assert len(signal.points) <= 42
    assert signal.points[0].observed_at == start
    assert signal.points[-1].observed_at == start + timedelta(seconds=1199)
    assert {value.observed_at for value in signal.points} >= {
        start + timedelta(seconds=23),
        start + timedelta(seconds=723),
    }
    assert missing.sample_count == 0
    assert missing.points == []


def test_database_rows_are_consumed_incrementally() -> None:
    session = Mock(spec=Session)
    start = datetime(2026, 9, 25, tzinfo=UTC)
    session.get.return_value = Mock(started_at=start, ended_at=start + timedelta(minutes=20))
    rows = [
        ("wifi.rssi_dbm", start, -60.0, 1),
        ("wifi.rssi_dbm", start + timedelta(minutes=20), -55.0, 2),
    ]
    session.execute.return_value = (row for row in rows)

    overviews = get_metric_overviews(session, "rec_test", ["wifi.rssi_dbm"], 20)

    assert overviews[0].sample_count == 2
    assert session.execute.call_args.args[0]._execution_options["yield_per"] == 1000
