"""Recovery after a completed manifest loses its in-process analysis task."""

from contextlib import nullcontext
from unittest.mock import Mock, patch

from sqlalchemy.dialects import postgresql
from wifi_server.services.analysis_recovery import (
    BATCH_SIZE,
    _recovery_loop,
    missing_analysis_ids,
    recover_pending_analyses,
)


def test_recovery_selects_only_current_missing_analyses() -> None:
    session = Mock()
    session.scalars.return_value.all.return_value = ["rec_pending"]

    assert missing_analysis_ids(session, "rec_earlier") == ["rec_pending"]

    statement = session.scalars.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "diagnostic_recordings.status =" in sql
    assert "diagnostic_recordings.sync_status =" in sql
    assert "NOT (EXISTS" in sql
    assert "recording_analyses.engine_version =" in sql
    assert "recording_analyses.source_metrics_count = diagnostic_recordings.metrics_count" in sql
    assert "recording_analyses.source_events_count = diagnostic_recordings.events_count" in sql
    assert "diagnostic_recordings.id >" in sql
    assert statement._limit_clause.value == BATCH_SIZE


def test_recovery_continues_after_failure_and_wraps_to_earlier_recordings() -> None:
    database = Mock()
    selection = Mock()
    database.session.side_effect = lambda: nullcontext(selection)

    with (
        patch("wifi_server.services.analysis_recovery.missing_analysis_ids") as find,
        patch("wifi_server.services.analysis_recovery.ensure_recording_analysis") as analyze,
    ):
        find.side_effect = [[], ["rec_a", "rec_b"]]
        analyze.side_effect = [RuntimeError("analysis interrupted"), None]

        assert recover_pending_analyses(database, "rec_z") == "rec_b"
        assert find.call_args_list[0].args[1] == "rec_z"
        assert find.call_args_list[1].args == (selection,)
        assert [item.args[1] for item in analyze.call_args_list] == ["rec_a", "rec_b"]


def test_recovery_loop_retries_after_scan_error() -> None:
    stop = Mock()
    stop.is_set.side_effect = [False, False, True]

    with (
        patch("wifi_server.services.analysis_recovery.get_database"),
        patch("wifi_server.services.analysis_recovery.recover_pending_analyses") as scan,
    ):
        scan.side_effect = [RuntimeError("database temporarily unavailable"), "rec_done"]
        _recovery_loop(stop)

    assert scan.call_count == 2
    assert stop.wait.call_count == 2
