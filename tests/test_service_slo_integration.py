import json
from datetime import UTC, datetime, timedelta

from wem.reports.html import render_html_report
from wem.storage.database import Database
from wem.storage.history import HistoryRepository
from wem.storage.models import SnapshotRecord


def test_history_and_report_summarize_fresh_service_executions(tmp_path):
    database = Database(str(tmp_path / "service-slo.db"))
    database.initialize()
    start = datetime(2026, 9, 22, 12, tzinfo=UTC)

    payloads = [
        {
            "connectivity": {
                "tests": {"dns": {"status": "passed", "fresh": True}},
                "dns_latency_ms": 10.0,
            }
        },
        {
            "connectivity": {
                "tests": {"dns": {"status": "passed", "fresh": True}},
                "dns_latency_ms": 30.0,
            }
        },
        {
            "connectivity": {
                "tests": {"dns": {"status": "failed", "fresh": True}},
                "dns_latency_ms": None,
            }
        },
        {
            "connectivity": {
                "tests": {"dns": {"status": "passed", "fresh": False}},
                "dns_latency_ms": 9999.0,
            }
        },
    ]
    with database.session() as session:
        for index, payload in enumerate(payloads, start=1):
            session.add(
                SnapshotRecord(
                    timestamp=(start + timedelta(seconds=index)).replace(tzinfo=None),
                    interface="wlan0",
                    snapshot_json=json.dumps(payload),
                )
            )
        session.commit()

    window = HistoryRepository(database).window(
        "wlan0",
        start,
        start + timedelta(minutes=1),
        10,
    )
    dns = window["service_slo_summary"]["dns"]

    assert dns["attempt_count"] == 3
    assert dns["availability_percent"] == 66.667
    assert dns["latency_ms"]["p95"] == 29.0

    html = render_html_report(window, [])
    assert "Synthetic service SLA/SLO observations" in html
    assert "66.67%" in html
