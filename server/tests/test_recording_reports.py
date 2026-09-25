"""HTML exports describe only persisted evidence and escape user-controlled context."""

from datetime import UTC, datetime

from wifi_server.db.analysis_models import RecordingAnalysis
from wifi_server.recording_schemas import RecordingResponse
from wifi_server.services.reports import render_recording_report


def _recording() -> RecordingResponse:
    now = datetime.now(UTC)
    return RecordingResponse(
        id="rec_test",
        agent_id="agt_test",
        project_id="prj_test",
        project_name="Office <script>alert(1)</script>",
        project_run_id="run_test",
        name="Wi-Fi <script>alert(1)</script>",
        description="Check <img src=x onerror=alert(1)>",
        site="HQ",
        location="Room 3",
        status="completed",
        sync_status="complete",
        profile_id="wifi-deep-dive",
        max_duration_minutes=30,
        started_at=now,
        ended_at=now,
        agent_version="0.1.0",
        schema_version=1,
        metrics_count=10,
        events_count=2,
        tests_count=0,
        artifacts_count=0,
        created_at=now,
        updated_at=now,
    )


def _analysis() -> RecordingAnalysis:
    return RecordingAnalysis(
        id="ana_test",
        recording_id="rec_test",
        engine_version="recording-analysis-v7",
        status="complete",
        source_metrics_count=10,
        source_events_count=2,
        summary={
            "status": "warning",
            "evidence_status": "partial",
            "rssi": {"average": -71.5, "p90": -60.0},
            "limitations": ["Collector paused <2s>"],
            "collection_integrity": {"status": "interrupted"},
            "disconnection_intervals": [
                {
                    "disconnected_at": "2026-09-25T12:00:00Z",
                    "reconnected_at": None,
                    "duration_seconds": None,
                    "status": "open",
                    "limitations": ["Reconnection was not observed"],
                }
            ],
        },
        findings=[
            {
                "severity": "warning",
                "code": "WIFI_TEST",
                "title": "Weak signal",
                "message": "RSSI dropped",
                "next_action": "Check the location",
            }
        ],
        policy={},
        created_at=datetime.now(UTC),
    )


def test_report_includes_analysis_and_escapes_recording_context() -> None:
    html = render_recording_report(_recording(), _analysis())

    assert "Weak signal" in html
    assert "recording-analysis-v7" in html
    assert "-71.5 dBm" in html
    assert "Reconnection was not observed" in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror=alert(1)>" not in html


def test_stale_or_incomplete_dataset_does_not_claim_findings() -> None:
    recording = _recording()
    recording.metrics_count = 11
    html = render_recording_report(recording, _analysis())
    assert "Analysis unavailable" in html
    assert "Weak signal" not in html

    recording.metrics_count = 10
    recording.sync_status = "incomplete"
    html = render_recording_report(recording, _analysis())
    assert "Analysis unavailable" in html
    assert "Weak signal" not in html
