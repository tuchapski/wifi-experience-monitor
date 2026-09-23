import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from wem.api.app import create_app
from wem.models.metrics import IncidentEvent
from wem.reports.html import render_html_report
from wem.storage.database import Database
from wem.storage.incidents import IncidentRepository
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
    incident_repository = IncidentRepository(database)
    incident_repository.process_event(
        IncidentEvent(
            action="opened",
            code="DNS_FAILURE",
            domain="dns",
            severity="critical",
            message="DNS failed",
            first_seen_at=(start + timedelta(minutes=9)).isoformat(),
            opened_at=(start + timedelta(minutes=10)).isoformat(),
            resolved_at=None,
        )
    )
    incident_repository.process_event(
        IncidentEvent(
            action="resolved",
            code="DNS_FAILURE",
            domain="dns",
            severity="critical",
            message="DNS failed",
            first_seen_at=(start + timedelta(minutes=9)).isoformat(),
            opened_at=(start + timedelta(minutes=10)).isoformat(),
            resolved_at=(start + timedelta(minutes=11)).isoformat(),
        )
    )
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
    assert "Wi-Fi Experience Executive Report" in response.text
    assert "Experience episodes<strong>1</strong>" in response.text
    assert "Previous equivalent period" in response.text
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


def test_report_renders_percentile_data_from_history():
    html = render_html_report(
        {
            "interface": "wlan0",
            "start": "2026-09-21T12:00:00+00:00",
            "end": "2026-09-21T13:00:00+00:00",
            "points": [
                {
                    "sample_count": 2,
                    "metrics": {
                        "signal_dbm": {
                            "avg": -65,
                            "min": -70,
                            "max": -60,
                            "count": 2,
                            "p50": -65,
                            "p95": -60.5,
                            "p99": -60.1,
                        }
                    },
                }
            ],
            "events": [],
        },
        [],
    )
    assert "Wi-Fi signal" in html


def test_report_v2_renders_episodes_comparison_and_escapes_episode_codes():
    html = render_html_report(
        {
            "interface": "wlan0",
            "start": "2026-09-21T12:00:00+00:00",
            "end": "2026-09-21T13:00:00+00:00",
            "points": [],
            "events": [],
            "service_slo_summary": {"dns": {"attempt_count": 10, "availability_percent": 90.0}},
            "comparison": {
                "current": {
                    "metrics": {
                        "dns_latency_ms": {"p95": 300.0},
                    }
                },
                "previous": {
                    "metrics": {
                        "dns_latency_ms": {"p95": 100.0},
                    }
                },
                "previous_start": "2026-09-21T11:00:00+00:00",
                "previous_end": "2026-09-21T12:00:00+00:00",
                "connection_cycles": {
                    "current": {"total_time_ms": {"p95": 5000.0}},
                    "previous": {"total_time_ms": {"p95": 3000.0}},
                },
                "service_slo": {
                    "current": {"dns": {"availability_percent": 90.0}},
                    "previous": {"dns": {"availability_percent": 99.0}},
                },
            },
        },
        [],
        [
            {
                "severity": "critical",
                "status": "ended",
                "started_at": "2026-09-21T12:10:00+00:00",
                "ended_at": "2026-09-21T12:12:00+00:00",
                "duration_seconds": 120.0,
                "incident_count": 2,
                "correlation_status": "correlated",
                "primary_domain": "dns",
                "codes": ["DNS<FAILURE>", "SERVICE_SLO_DNS"],
            }
        ],
    )

    assert "Executive overview" in html
    assert "Experience episodes" in html
    assert "Period-over-period comparison" in html
    assert "DNS&lt;FAILURE&gt;" in html
    assert "+200.00 ms" in html
    assert "Lowest measured synthetic-service availability" in html
