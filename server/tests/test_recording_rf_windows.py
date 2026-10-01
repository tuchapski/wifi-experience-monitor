from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from wifi_server.api.recordings import router
from wifi_server.db.models import DiagnosticRecording
from wifi_server.dependencies import get_session
from wifi_server.services.rf_windows import get_recording_rf_windows

END = datetime(2026, 10, 1, 12, tzinfo=UTC)


def session_with(rows, total=None):
    session = Mock(spec=Session)
    session.get.return_value = DiagnosticRecording(id="rec_test")
    session.scalar.return_value = len(rows) if total is None else total
    session.execute.return_value.all.return_value = rows
    return session


def test_windows_use_completion_minus_duration_and_keep_interface():
    session = session_with(
        [
            ("new", "wlan1", END, 1500.5),
            ("old", "wlan0", END - timedelta(minutes=1), 0),
        ],
        total=3,
    )
    result = get_recording_rf_windows(session, "rec_test", limit=2)
    assert result.total_scans == 3
    assert result.loaded_scans == 2
    assert result.truncated is True
    assert [window.scan_id for window in result.windows] == ["old", "new"]
    assert result.windows[1].started_at == END - timedelta(milliseconds=1500.5)
    assert result.windows[1].ended_at == END
    assert result.windows[1].interface == "wlan1"
    assert result.windows[0].started_at == result.windows[0].ended_at


@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf"), 1e300, None])
def test_invalid_durations_are_counted_and_omitted(duration):
    result = get_recording_rf_windows(session_with([("bad", "wlan0", END, duration)]), "rec_test")
    assert result.invalid_windows == 1
    assert result.loaded_scans == result.total_scans == 1
    assert result.windows == []
    assert not result.truncated


def test_real_query_is_scoped_bounded_and_needs_no_bss_inventory():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE agent_rf_scans (id INTEGER, scan_id TEXT, interface TEXT, "
            "observed_at DATETIME, duration_ms FLOAT, recording_id TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO agent_rf_scans VALUES "
            "(1, 'first', 'wlan0', '2026-10-01 12:00:00', 500, 'rec_test'), "
            "(2, 'second', 'wlan0', '2026-10-01 12:00:00', 700, 'rec_test'), "
            "(3, 'other', 'wlan1', '2026-10-01 13:00:00', 900, 'rec_other')"
        )
        session = session_with([])
        session.scalar.side_effect = connection.scalar
        session.execute.side_effect = connection.execute
        result = get_recording_rf_windows(session, "rec_test", limit=1)
    assert result.total_scans == 2
    assert result.loaded_scans == 1
    assert result.truncated
    assert result.windows[0].scan_id == "second"
    assert result.windows[0].duration_ms == 700


def test_unknown_recording_stops_before_scan_query():
    session = session_with([])
    session.get.return_value = None
    with pytest.raises(HTTPException) as error:
        get_recording_rf_windows(session, "missing")
    assert error.value.status_code == 404
    session.scalar.assert_not_called()
    session.execute.assert_not_called()


def test_endpoint_empty_serialization_and_limit_validation():
    session = session_with([])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        assert client.get("/api/v1/recordings/rec_test/rf/windows").json() == {
            "total_scans": 0,
            "loaded_scans": 0,
            "invalid_windows": 0,
            "truncated": False,
            "windows": [],
        }
        for limit in (0, 2001):
            assert (
                client.get(f"/api/v1/recordings/rec_test/rf/windows?limit={limit}").status_code
                == 422
            )
        session.execute.return_value.all.return_value = [("scan", "wlan0", END, 1000)]
        session.scalar.return_value = 1
        response = client.get("/api/v1/recordings/rec_test/rf/windows?limit=1")
        assert response.status_code == 200
        assert response.json()["windows"][0]["started_at"] == "2026-10-01T11:59:59Z"
        session.get.return_value = None
        assert client.get("/api/v1/recordings/missing/rf/windows").status_code == 404
