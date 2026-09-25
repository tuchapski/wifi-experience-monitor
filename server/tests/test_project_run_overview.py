"""Project run summaries preserve each Agent's own analysis and evidence state."""

from datetime import UTC, datetime
from unittest.mock import Mock

from sqlalchemy.orm import Session
from wifi_server.db.analysis_models import RecordingAnalysis
from wifi_server.db.project_models import ProjectRun, ProjectRunRecording
from wifi_server.services.projects import _run_response


def _analysis() -> RecordingAnalysis:
    return RecordingAnalysis(
        id="ana_test",
        recording_id="rec_agt_1",
        engine_version="recording-analysis-v7",
        status="complete",
        source_metrics_count=10,
        source_events_count=2,
        summary={"status": "critical", "evidence_status": "partial"},
        findings=[
            {"code": "WARNING", "severity": "warning", "title": "Retries"},
            {"code": "CRITICAL", "severity": "critical", "title": "Disconnection"},
        ],
        policy={},
        created_at=datetime.now(UTC),
    )


def test_latest_analysis_is_shown_only_for_its_agent() -> None:
    session = Mock(spec=Session)
    run = ProjectRun(id="run_test", project_id="prj_test", started_at=datetime.now(UTC))
    members = [
        ProjectRunRecording(run_id="run_test", agent_id=agent_id, recording_id=f"rec_{agent_id}")
        for agent_id in ("agt_1", "agt_2")
    ]
    session.scalars.return_value.all.side_effect = [members, [_analysis()]]
    session.get.side_effect = lambda model, key: Mock(
        status="completed",
        sync_status="complete",
        metrics_count=10,
        events_count=2,
        location="West lounge" if key == "rec_agt_1" else "Floor 3",
    )

    result = _run_response(session, run)

    first = next(item for item in result.recordings if item.agent_id == "agt_1")
    second = next(item for item in result.recordings if item.agent_id == "agt_2")
    assert first.analysis.assessment == "critical"
    assert first.analysis.evidence_status == "partial"
    assert [finding.code for finding in first.analysis.top_findings] == ["CRITICAL", "WARNING"]
    assert second.analysis is None
    assert first.location == "West lounge"
    assert second.location == "Floor 3"


def test_active_or_resynchronizing_recordings_do_not_show_stale_analysis() -> None:
    for status, sync_status in (("recording", "pending"), ("completed", "syncing")):
        session = Mock(spec=Session)
        run = ProjectRun(id="run_test", project_id="prj_test", started_at=datetime.now(UTC))
        member = ProjectRunRecording(run_id="run_test", agent_id="agt_1", recording_id="rec_agt_1")
        session.scalars.return_value.all.return_value = [member]
        session.get.return_value = Mock(status=status, sync_status=sync_status, location=None)

        result = _run_response(session, run)

        assert result.recordings[0].analysis is None
        assert session.scalars.return_value.all.call_count == 1


def test_analysis_with_different_metric_count_is_excluded() -> None:
    session = Mock(spec=Session)
    run = ProjectRun(id="run_test", project_id="prj_test", started_at=datetime.now(UTC))
    member = ProjectRunRecording(run_id="run_test", agent_id="agt_1", recording_id="rec_agt_1")
    session.scalars.return_value.all.side_effect = [[member], [_analysis()]]
    session.get.return_value = Mock(
        status="completed",
        sync_status="complete",
        metrics_count=11,
        events_count=2,
        location=None,
    )

    result = _run_response(session, run)

    assert result.recordings[0].analysis is None
