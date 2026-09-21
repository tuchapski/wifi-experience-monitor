import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from wem.api.app import create_app
from wem.reports.html import render_html_report
from wem.storage.database import Database
from wem.storage.models import SnapshotRecord


def test_report_escapes_user_values_and_contains_sections():
    html = render_html_report(
        {
            "interface": "wlan<script>",
            "start": "2026-09-21T12:00:00+00:00",
            "end": "2026-09-21T13:00:00+00:00",
            "points": [],
            "events": [
                {
                    "timestamp": "2026-09-21T12:10:00+00:00",
                    "field": "SSID",
                    "message": "SSID changed: <old> → <new>.",
                }
            ],
        },
        [],
    )
    assert "wlan&lt;script&gt;" in html
    assert "SSID changed: &lt;old&gt;" in html
    assert "Measurements" in html
    assert "Environment changes" in html
    assert "Interpretation and limitations" in html


def test_html_report_endpoint_filters_incidents_by_period(tmp_path):
    path = str(tmp_path / "report.db")
    database = Database(path)
    database.initialize()
    start = datetime(2026, 9, 21, 12, tzinfo=UTC)
    snapshot = {
        "environment_changes": [],
        "wifi": {"signal_dbm": -60},
    }
    with database.session() as session:
        session.add(
            SnapshotRecord(
                timestamp=(start + timedelta(minutes=1)).replace(tzinfo=None),
                interface="wlan0",
                signal_dbm=-60,
                snapshot_json=json.dumps(snapshot),
            )
        )
        session.commit()
    with TestClient(create_app(path)) as client:
        response = client.get(
            "/reports/html",
            params={
                "interface": "wlan0",
                "start": start.isoformat(),
                "end": (start + timedelta(hours=1)).isoformat(),
            },
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Wi-Fi Experience Monitor report" in response.text
    assert "wlan0" in response.text


def test_html_report_rejects_invalid_range(tmp_path):
    with TestClient(create_app(str(tmp_path / "invalid.db"))) as client:
        response = client.get(
            "/reports/html",
            params={
                "interface": "wlan0",
                "start": "2026-09-21T12:00:00+00:00",
                "end": "2026-09-21T12:00:00+00:00",
            },
        )
    assert response.status_code == 422
