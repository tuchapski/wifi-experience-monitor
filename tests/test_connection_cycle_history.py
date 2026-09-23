import json
from datetime import UTC, datetime, timedelta

from wem.reports.html import render_html_report
from wem.storage.database import Database
from wem.storage.history import HistoryRepository
from wem.storage.models import SnapshotRecord

START = datetime(2026, 9, 22, 12, tzinfo=UTC)


def cycle(state: str, observed_at: str) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "session_type": "reconnect",
        "state": state,
        "ssid": "CORP<WiFi>",
        "bssid": "aa:bb:cc:dd:ee:ff",
        "started_at": START.isoformat(),
        "last_observed_at": observed_at,
        "completed_at": None,
        "total_time_ms": 5000.0 if state == "ready" else None,
        "sample_resolution_ms": 5000.0,
        "stages": {
            "network_ready": {
                "status": "observed" if state == "ready" else "pending",
                "observed_at": observed_at if state == "ready" else None,
                "elapsed_ms": 5000.0 if state == "ready" else None,
                "estimated": state == "ready",
                "reason": "poll-derived",
            }
        },
        "limitations": ["Estimated from periodic samples."],
    }


def test_history_deduplicates_cycle_and_keeps_latest_state(tmp_path):
    db = Database(str(tmp_path / "cycles.db"))
    db.initialize()
    with db.session() as session:
        for seconds, state in [(1, "connecting"), (6, "ready")]:
            observed = (START + timedelta(seconds=seconds)).isoformat()
            session.add(
                SnapshotRecord(
                    timestamp=(START + timedelta(seconds=seconds)).replace(tzinfo=None),
                    interface="wlan0",
                    snapshot_json=json.dumps({"connection_cycle": cycle(state, observed)}),
                )
            )
        session.commit()

    result = HistoryRepository(db).window("wlan0", START, START + timedelta(minutes=1))
    assert len(result["connection_cycles"]) == 1
    assert result["connection_cycles"][0]["state"] == "ready"
    assert result["connection_cycles"][0]["total_time_ms"] == 5000.0
    summary = result["connection_cycle_summary"]
    assert summary["total_cycles"] == 1
    assert summary["measurable_cycles"] == 1
    assert summary["total_time_ms"]["p50"] == 5000.0
    assert summary["total_time_ms"]["p95"] == 5000.0
    assert summary["stages"]["network_ready"]["p50"] == 5000.0


def test_report_renders_connection_cycles_and_escapes_ssid():
    html = render_html_report(
        {
            "interface": "wlan0",
            "start": START.isoformat(),
            "end": (START + timedelta(minutes=1)).isoformat(),
            "points": [],
            "events": [],
            "connection_cycles": [cycle("ready", (START + timedelta(seconds=5)).isoformat())],
            "connection_cycle_summary": {
                "total_cycles": 1,
                "measurable_cycles": 1,
                "by_type": {"reconnect": 1},
                "total_time_ms": {"p50": 5000.0, "p95": 5000.0},
                "stages": {
                    "network_ready": {
                        "count": 1,
                        "p50": 5000.0,
                        "p95": 5000.0,
                        "p99": 5000.0,
                    }
                },
            },
        },
        [],
    )
    assert "Connection cycles" in html
    assert "CORP&lt;WiFi&gt;" in html
    assert "5000.00 ms" in html
    assert "Connection cycle statistics" in html
    assert "Stage timing percentiles" in html
