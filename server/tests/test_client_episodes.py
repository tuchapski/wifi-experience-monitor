from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from test_client_monitor_persistence import _jsonb_as_sqlite_json  # noqa: F401
from test_continuous_detection import NOW, VERSION, step
from wifi_server.db.base import Base
from wifi_server.db.episode_models import ClientEpisode, EpisodeCapture, EpisodeEvent
from wifi_server.db.experience_models import AgentExperienceMonitor
from wifi_server.db.models import Agent, AgentCurrentState, DiagnosticRecording
from wifi_server.db.project_models import DiagnosticProject, ProjectRun, ProjectRunRecording
from wifi_server.db.recording_models import AgentCommand, RecordingMetric
from wifi_server.monitor_schemas import ExperienceProfile, ExperienceProfileUpdate
from wifi_server.recording_schemas import AgentCommandAckRequest
from wifi_server.services.client_episodes import (
    acknowledge_episode,
    finalize_capture_coverage,
    get_episode,
    list_episodes,
    synchronize_episodes,
)
from wifi_server.services.client_monitor import update_profile
from wifi_server.services.recordings import acknowledge_command


@compiles(BigInteger, "sqlite")
def _bigint_as_sqlite_integer(_type, _compiler, **_kw):
    return "INTEGER"


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'episodes.db'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                Agent,
                AgentCurrentState,
                AgentExperienceMonitor,
                ClientEpisode,
                EpisodeEvent,
                EpisodeCapture,
                DiagnosticRecording,
                AgentCommand,
                RecordingMetric,
                DiagnosticProject,
                ProjectRun,
                ProjectRunRecording,
            )
        ],
    )
    with Session(engine) as session:
        session.add(
            Agent(
                id="agt_test",
                name="Test",
                hostname="Test",
                agent_type="sensor",
                status="online",
                agent_version="1",
                first_seen_at=NOW,
                last_seen_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            AgentExperienceMonitor(
                agent_id="agt_test",
                profile_version=VERSION,
                profile=ExperienceProfile(enabled=True).model_dump(mode="json"),
                detector_state={},
                updated_at=NOW,
            )
        )
        session.commit()
    return engine


def ingest(engine, seconds, *, profile=None, **changes):
    profile = profile or ExperienceProfile(enabled=True)
    with Session(engine) as session:
        monitor = session.get(AgentExperienceMonitor, "agt_test")
        monitor.detector_state = step(monitor.detector_state, seconds, profile=profile, **changes)
        synchronize_episodes(session, monitor, profile, NOW + timedelta(seconds=seconds))
        session.commit()


def test_episode_recovery_recurrence_ack_and_client_scope(engine):
    for second in (0, 5, 10, 15):
        ingest(engine, second, gateway_latency_ms=100, gateway_packet_loss_percent=25)
    with Session(engine) as session:
        episodes = session.scalars(select(ClientEpisode)).all()
        assert len(episodes) == 1  # Same client, domain, target, context.
        episode_id = episodes[0].id
        assert len(episodes[0].evidence["rules"]) == 2
        acknowledge_episode(session, "agt_test", episode_id)
        acknowledge_episode(session, "agt_test", episode_id)
        assert session.get(ClientEpisode, episode_id).status == "active"
        assert (
            len(
                session.scalars(
                    select(EpisodeEvent).where(EpisodeEvent.kind == "acknowledged")
                ).all()
            )
            == 1
        )
        with pytest.raises(HTTPException) as exc:
            acknowledge_episode(session, "agt_other", episode_id)
        assert exc.value.status_code == 404
    for second in (20, 25, 30):
        ingest(engine, second)
    with Session(engine) as session:
        episode = session.get(ClientEpisode, episode_id)
        assert episode.status == "recovered" and episode.closed_at is not None
    for second in (40, 45, 50, 55):
        ingest(engine, second, gateway_latency_ms=100)
    with Session(engine) as session:
        episode = session.get(ClientEpisode, episode_id)
        assert episode.status == "active" and episode.closed_at is None
        assert episode.recurrence_count == 1
        assert len(session.scalars(select(ClientEpisode)).all()) == 1


def test_gaps_do_not_recover_duration_or_rewrite_history_and_profile_interrupts(engine):
    for second in (0, 5, 10, 15):
        ingest(engine, second, gateway_latency_ms=100)
    with Session(engine) as session:
        episode = session.scalar(select(ClientEpisode))
        episode_id = episode.id
        with patch("wifi_server.services.client_episodes.datetime") as clock:
            clock.now.return_value = NOW + timedelta(seconds=100)
            response = get_episode(session, "agt_test", episode_id, 30)
            assert response.status == "unknown" and response.evidence_gap
            assert response.stored_status == "active" and response.recovered_at is None
        assert episode.status == "active"
    ingest(engine, 100, gateway_latency_ms=100)
    with Session(engine) as session:
        episode = session.get(ClientEpisode, episode_id)
        assert episode.observed_duration_seconds == 15
        assert episode.evidence["gap_count"] == 1
        update_profile(
            session,
            "agt_test",
            ExperienceProfileUpdate(
                expected_version=VERSION, profile=ExperienceProfile(enabled=False)
            ),
            track_episodes=True,
        )
        episode = session.get(ClientEpisode, episode_id)
        assert episode.status == "interrupted" and episode.recovered_at is None


def test_capture_reuses_manual_recording_and_failure_keeps_it_active(engine):
    with Session(engine) as session:
        recording = DiagnosticRecording(
            id="rec_manual",
            agent_id="agt_test",
            name="Manual",
            status="recording",
            sync_status="pending",
            schema_version=1,
            metrics_count=0,
            events_count=0,
            tests_count=0,
            artifacts_count=0,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(recording)
        session.commit()
    ingest(
        engine,
        0,
        profile=ExperienceProfile(enabled=True, automatic_capture=True),
        https_success=False,
    )
    with Session(engine) as session:
        capture = session.scalar(select(EpisodeCapture))
        command = session.scalar(select(AgentCommand))
        assert capture.mode == "reused" and capture.recording_id == "rec_manual"
        assert command.payload["profile_version"] == VERSION
        acknowledge_command(
            session, command, AgentCommandAckRequest(status="failed", message="expired")
        )
        assert session.get(DiagnosticRecording, "rec_manual").status == "recording"
        assert capture.status == "failed"
        acknowledge_command(session, command, AgentCommandAckRequest(status="acked"))
        assert capture.status == "failed"  # Terminal acknowledgement stays idempotent.


def test_auto_capture_single_recording_multiple_domains_and_coverage(engine):
    profile = ExperienceProfile(
        enabled=True, automatic_capture=True, capture_pre_seconds=0, capture_post_seconds=30
    )
    ingest(engine, 0, profile=profile, https_success=False, internet_reachable=False)
    with Session(engine) as session:
        captures = session.scalars(select(EpisodeCapture)).all()
        assert len(captures) == 2
        assert {item.mode for item in captures} == {"automatic", "reused"}
        recording = session.scalar(select(DiagnosticRecording))
        assert len(session.scalars(select(DiagnosticRecording)).all()) == 1
        commands = session.scalars(select(AgentCommand)).all()
        for command in commands:
            acknowledge_command(
                session,
                command,
                AgentCommandAckRequest(status="acked", data={"started_at": NOW.isoformat()}),
            )
        for second in range(31):
            session.add(
                RecordingMetric(
                    recording_id=recording.id,
                    metric="sensor.collection_cycle",
                    observed_at=NOW + timedelta(seconds=second),
                    value=1,
                    labels={},
                    received_at=NOW,
                )
            )
        recording.sync_status = "complete"
        finalize_capture_coverage(session, recording)
        session.commit()
        assert all(item.status == "complete" for item in captures)
        recording.sync_status = "incomplete"
        finalize_capture_coverage(session, recording)
        session.commit()
        assert all(item.status == "partial" for item in captures)
        with patch("wifi_server.services.client_episodes.datetime") as clock:
            clock.now.return_value = NOW
            page = list_episodes(session, "agt_test", 30, offset=0, limit=1, domain="application")
            assert page.total == 1 and len(page.episodes) == 1


def test_new_episode_after_recovery_window_obeys_capture_cooldown(engine):
    profile = ExperienceProfile(enabled=True, automatic_capture=True)
    ingest(engine, 0, profile=profile, https_success=False)
    for second in (5, 10, 15):
        ingest(engine, second, profile=profile)
    with Session(engine) as session:
        first = session.scalar(select(ClientEpisode))
        first_id = first.id
        assert first.status == "recovered"
        recording = session.scalar(select(DiagnosticRecording))
        recording.status = "completed"
        session.commit()
    ingest(engine, 100, profile=profile, https_success=False)
    with Session(engine) as session:
        episodes = session.scalars(select(ClientEpisode).order_by(ClientEpisode.started_at)).all()
        assert len(episodes) == 2 and episodes[1].id != first_id
        second_capture = session.get(EpisodeCapture, episodes[1].id)
        assert second_capture.status == "skipped"
        assert second_capture.recording_id is None
        assert len(session.scalars(select(DiagnosticRecording)).all()) == 1


def test_context_change_interrupts_without_recovery_and_keeps_opening_reading(engine):
    for second in (0, 5, 10, 15):
        ingest(engine, second, gateway_latency_ms=100)
    ingest(engine, 20, wifi={"ssid": "Meeting room"})
    with Session(engine) as session:
        episode = session.scalar(select(ClientEpisode))
        assert episode.status == "interrupted" and episode.recovered_at is None
        assert episode.evidence["opening_findings"][0]["value"] == 100
        assert episode.context["ssid"] == "Office"


def test_existing_profile_defaults_do_not_reset_version_on_unchanged_save(engine):
    with Session(engine) as session:
        monitor = session.get(AgentExperienceMonitor, "agt_test")
        monitor.profile = {
            key: value
            for key, value in monitor.profile.items()
            if key
            not in {
                "automatic_capture",
                "capture_pre_seconds",
                "capture_post_seconds",
                "capture_cooldown_seconds",
            }
        }
        session.commit()
        saved = update_profile(
            session,
            "agt_test",
            ExperienceProfileUpdate(
                expected_version=VERSION, profile=ExperienceProfile(enabled=True)
            ),
            track_episodes=True,
        )
        assert saved.version == VERSION
        assert saved.profile.automatic_capture is False


def test_delayed_ack_after_completed_manifest_finishes_capture_coverage(engine):
    ingest(
        engine,
        0,
        profile=ExperienceProfile(enabled=True, automatic_capture=True),
        https_success=False,
    )
    with Session(engine) as session:
        recording = session.scalar(select(DiagnosticRecording))
        recording.status = "completed"
        recording.sync_status = "complete"
        session.commit()
        command = session.scalar(select(AgentCommand))
        acknowledge_command(
            session,
            command,
            AgentCommandAckRequest(
                status="acked", data={"started_at": NOW.isoformat(), "buffer_cycles": 0}
            ),
        )
        capture = session.scalar(select(EpisodeCapture))
        assert capture.status == "partial"
        assert capture.coverage["window_complete"] is False
        assert session.get(DiagnosticRecording, recording.id).status == "completed"
