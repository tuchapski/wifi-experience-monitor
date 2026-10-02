from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wifi_server.db.episode_models import ClientEpisode, EpisodeCapture, EpisodeEvent
from wifi_server.db.experience_models import AgentExperienceMonitor
from wifi_server.db.models import Agent, DiagnosticRecording
from wifi_server.db.project_models import ProjectRunRecording
from wifi_server.db.recording_models import AgentCommand, RecordingMetric
from wifi_server.episode_schemas import (
    ClientEpisodePage,
    ClientEpisodeResponse,
    EpisodeCaptureResponse,
    EpisodeTransition,
)
from wifi_server.monitor_schemas import DetectionFinding, ExperienceProfile
from wifi_server.services.agents import is_agent_online
from wifi_server.services.client_experience import _utc


def event(session: Session, episode: ClientEpisode, kind: str, time: datetime, data: dict) -> None:
    session.add(
        EpisodeEvent(
            id=f"evt_{uuid4().hex}", episode_id=episode.id, kind=kind, observed_at=time, data=data
        )
    )


def interrupt_episodes(session: Session, agent_id: str, reason: str, now: datetime) -> None:
    for episode in session.scalars(
        select(ClientEpisode).where(
            ClientEpisode.agent_id == agent_id, ClientEpisode.closed_at.is_(None)
        )
    ).all():
        episode.status = "interrupted"
        episode.closed_at = now
        episode.reason = reason
        event(session, episode, "interrupted", now, {"reason": reason, "recovery_confirmed": False})


def _request_capture(
    session: Session,
    monitor: AgentExperienceMonitor,
    episode: ClientEpisode,
    profile: ExperienceProfile,
    now: datetime,
) -> None:
    if not profile.automatic_capture or session.get(EpisodeCapture, episode.id) is not None:
        return
    start = _utc(episode.started_at) - timedelta(seconds=profile.capture_pre_seconds)
    end = _utc(episode.confirmed_at) + timedelta(seconds=profile.capture_post_seconds)
    active = session.scalar(
        select(DiagnosticRecording).where(
            DiagnosticRecording.agent_id == episode.agent_id,
            DiagnosticRecording.status.in_(("created", "recording", "stopping")),
        )
    )
    capture = EpisodeCapture(
        episode_id=episode.id,
        recording_id=None,
        mode="automatic",
        status="requested",
        requested_start=start,
        requested_end=end,
        coverage={},
    )
    session.add(capture)
    if active and session.scalar(
        select(ProjectRunRecording).where(ProjectRunRecording.recording_id == active.id)
    ):
        capture.mode, capture.status, capture.coverage = (
            "blocked",
            "skipped",
            {
                "reason": "A legacy project recording is active; "
                "no coordinated recording was changed."
            },
        )
        return
    if active is None:
        last = (monitor.detector_state or {}).get("last_capture_at")
        if (
            last
            and (now - datetime.fromisoformat(last)).total_seconds()
            < profile.capture_cooldown_seconds
        ):
            capture.status, capture.coverage = (
                "skipped",
                {"reason": "Client capture cooldown is active."},
            )
            return
        agent = session.get(Agent, episode.agent_id)
        active = DiagnosticRecording(
            id=f"rec_{uuid4().hex}",
            agent_id=episode.agent_id,
            name=f"Automatic · {episode.domain}",
            description=f"Evidence for episode {episode.id}",
            status="created",
            sync_status="pending",
            profile_id=episode.profile_version,
            max_duration_minutes=max(1, (profile.capture_post_seconds + 59) // 60),
            site=None,
            location=profile.location or None,
            agent_version=agent.agent_version,
            schema_version=1,
            metrics_count=0,
            events_count=0,
            tests_count=0,
            artifacts_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(active)
        session.flush()
        monitor.detector_state = {**monitor.detector_state, "last_capture_at": now.isoformat()}
    else:
        capture.mode = "reused"
    capture.recording_id = active.id
    session.add(
        AgentCommand(
            id=f"cmd_{uuid4().hex}",
            agent_id=episode.agent_id,
            command_type="recording.capture",
            payload={
                "episode_id": episode.id,
                "recording_id": active.id,
                "profile_version": monitor.profile_version,
                "mode": capture.mode,
                "window_start": start.isoformat(),
                "trigger_at": _utc(episode.confirmed_at).isoformat(),
                "window_end": end.isoformat(),
            },
            status="pending",
            created_at=now,
        )
    )
    event(
        session,
        episode,
        "capture_requested",
        now,
        {
            "recording_id": active.id,
            "mode": capture.mode,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
        },
    )


def synchronize_episodes(
    session: Session, monitor: AgentExperienceMonitor, profile: ExperienceProfile, now: datetime
) -> None:
    groups = {}
    for rule in (monitor.detector_state or {}).get("rules", {}).values():
        context = rule.get("context")
        if not context or "domain" not in rule:
            continue
        scope = sha256(repr((rule["domain"], sorted(context.items()))).encode()).hexdigest()
        groups.setdefault(scope, {})[rule["rule_id"]] = rule
    opened = {
        item.scope_key: item
        for item in session.scalars(
            select(ClientEpisode).where(
                ClientEpisode.agent_id == monitor.agent_id, ClientEpisode.closed_at.is_(None)
            )
        ).all()
    }
    for scope, episode in opened.items():
        if scope not in groups:
            episode.status, episode.closed_at = "interrupted", now
            episode.reason = "Comparable context changed; recovery was not confirmed."
            event(session, episode, "interrupted", now, {"reason": episode.reason})
    for scope, rules in groups.items():
        active = [rule for rule in rules.values() if rule.get("status") == "active"]
        episode = opened.get(scope)
        if episode is None and not active:
            continue
        if episode is None:
            episode = session.scalar(
                select(ClientEpisode)
                .where(
                    ClientEpisode.agent_id == monitor.agent_id,
                    ClientEpisode.scope_key == scope,
                    ClientEpisode.status == "recovered",
                    ClientEpisode.closed_at >= now - timedelta(seconds=60),
                )
                .order_by(ClientEpisode.closed_at.desc())
                .limit(1)
            )
            if episode:
                episode.closed_at = None
                episode.recovered_at = None
                episode.acknowledged_at = None
                episode.recurrence_count += 1
                episode.evidence = {
                    **episode.evidence,
                    "duration_base": episode.observed_duration_seconds,
                    "rules": {},
                }
                event(session, episode, "reopened", now, {"recurrence": episode.recurrence_count})
            else:
                first = active[0]
                times = [
                    datetime.fromisoformat(rule.get("since") or rule["observed_at"])
                    for rule in active
                ]
                confirmed = max(datetime.fromisoformat(rule["observed_at"]) for rule in active)
                episode = ClientEpisode(
                    id=f"ep_{uuid4().hex}",
                    agent_id=monitor.agent_id,
                    scope_key=scope,
                    domain=first["domain"],
                    target=first.get("target"),
                    profile_version=monitor.profile_version,
                    detector_version="client-detector-v1",
                    status="active",
                    started_at=min(times),
                    confirmed_at=confirmed,
                    last_observed_at=confirmed,
                    recurrence_count=0,
                    observed_duration_seconds=0,
                    reason=first.get("reason", "Confirmed rule"),
                    context=first["context"],
                    evidence={"rules": {}, "gap_count": 0, "opening_findings": active},
                )
                session.add(episode)
                session.flush()
                event(
                    session,
                    episode,
                    "opened",
                    confirmed,
                    {
                        "findings": [
                            DetectionFinding.model_validate(rule).model_dump(mode="json")
                            for rule in active
                        ]
                    },
                )
        previous_status = episode.status
        tracked = dict((episode.evidence or {}).get("rules", {}))
        for key, rule in rules.items():
            if key in tracked or rule.get("status") == "active":
                tracked[key] = rule
        statuses = {rule.get("status") for rule in tracked.values()}
        phase = (
            "active"
            if "active" in statuses
            else "unknown"
            if "unknown" in statuses or "candidate" in statuses
            else "recovering"
            if "recovering" in statuses
            else "recovered"
        )
        times = [
            datetime.fromisoformat(rule["observed_at"])
            for rule in tracked.values()
            if rule.get("observed_at") and rule.get("status") != "unknown"
        ]
        last = max(times, default=_utc(episode.last_observed_at))
        evidence = {**episode.evidence, "rules": tracked}
        if last > _utc(episode.last_observed_at) + timedelta(seconds=30):
            evidence["gap_count"] = evidence.get("gap_count", 0) + 1
            event(
                session,
                episode,
                "evidence_gap",
                last,
                {"from": _utc(episode.last_observed_at).isoformat(), "to": last.isoformat()},
            )
        episode.last_observed_at = max(last, _utc(episode.last_observed_at))
        episode.observed_duration_seconds = max(
            episode.observed_duration_seconds,
            evidence.get("duration_base", 0)
            + max(
                (rule.get("observed_duration_seconds", 0) for rule in tracked.values()), default=0
            ),
        )
        episode.evidence = evidence
        episode.status = phase
        episode.reason = next(
            (rule.get("reason", "") for rule in tracked.values() if rule.get("status") == phase),
            episode.reason,
        )
        if phase == "recovered":
            episode.recovered_at = episode.closed_at = last
        if phase != previous_status:
            event(
                session,
                episode,
                phase,
                last if phase != "unknown" else now,
                {"reason": episode.reason},
            )
        _request_capture(session, monitor, episode, profile, now)


def _response(
    session: Session, episode: ClientEpisode, *, now: datetime, online: bool, detail: bool
) -> ClientEpisodeResponse:
    stale = episode.closed_at is None and (
        not online or (now - _utc(episode.last_observed_at)).total_seconds() > 30
    )
    capture = session.get(EpisodeCapture, episode.id)
    transitions = (
        session.scalars(
            select(EpisodeEvent)
            .where(EpisodeEvent.episode_id == episode.id)
            .order_by(EpisodeEvent.observed_at.desc(), EpisodeEvent.id.desc())
            .limit(201)
        ).all()
        if detail
        else []
    )
    return ClientEpisodeResponse(
        id=episode.id,
        agent_id=episode.agent_id,
        domain=episode.domain,
        target=episode.target,
        profile_version=episode.profile_version,
        detector_version=episode.detector_version,
        status="unknown" if stale else episode.status,
        stored_status=episode.status,
        started_at=_utc(episode.started_at),
        confirmed_at=_utc(episode.confirmed_at),
        last_observed_at=_utc(episode.last_observed_at),
        recovered_at=_utc(episode.recovered_at) if episode.recovered_at else None,
        closed_at=_utc(episode.closed_at) if episode.closed_at else None,
        acknowledged_at=_utc(episode.acknowledged_at) if episode.acknowledged_at else None,
        recurrence_count=episode.recurrence_count,
        observed_duration_seconds=episode.observed_duration_seconds,
        evidence_gap=stale
        or bool(episode.evidence.get("gap_count"))
        or any(rule.get("evidence_gap") for rule in episode.evidence.get("rules", {}).values()),
        reason="Current evidence is stale or Agent is offline; recovery remains unconfirmed."
        if stale
        else episode.reason,
        context=episode.context,
        opening_findings=[
            DetectionFinding.model_validate(rule)
            for rule in episode.evidence.get("opening_findings", [])
        ],
        findings=[
            DetectionFinding.model_validate(rule)
            for rule in episode.evidence.get("rules", {}).values()
        ],
        capture=EpisodeCaptureResponse(
            recording_id=capture.recording_id,
            mode=capture.mode,
            status=capture.status,
            requested_start=capture.requested_start,
            requested_end=capture.requested_end,
            coverage=capture.coverage,
        )
        if capture
        else None,
        transitions=[
            EpisodeTransition(kind=item.kind, observed_at=item.observed_at, data=item.data)
            for item in reversed(transitions[:200])
        ],
        transitions_truncated=len(transitions) > 200,
    )


def _get(session: Session, agent_id: str, episode_id: str) -> ClientEpisode:
    episode = session.get(ClientEpisode, episode_id)
    if episode is None or episode.agent_id != agent_id:
        raise HTTPException(404, "Episode not found for this client")
    return episode


def list_episodes(
    session: Session,
    agent_id: str,
    offline_seconds: float,
    *,
    offset: int,
    limit: int,
    domain: str | None = None,
) -> ClientEpisodePage:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    now = datetime.now(UTC)
    where = [ClientEpisode.agent_id == agent_id]
    if domain:
        where.append(ClientEpisode.domain == domain)
    total = session.scalar(select(func.count()).select_from(ClientEpisode).where(*where))
    records = session.scalars(
        select(ClientEpisode)
        .where(*where)
        .order_by(ClientEpisode.started_at.desc(), ClientEpisode.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    online = is_agent_online(_utc(agent.last_seen_at), now, offline_seconds)
    return ClientEpisodePage(
        agent_id=agent_id,
        evaluated_at=now,
        total=total,
        offset=offset,
        limit=limit,
        episodes=[
            _response(session, item, now=now, online=online, detail=False) for item in records
        ],
    )


def get_episode(
    session: Session, agent_id: str, episode_id: str, offline_seconds: float
) -> ClientEpisodeResponse:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    now = datetime.now(UTC)
    return _response(
        session,
        _get(session, agent_id, episode_id),
        now=now,
        online=is_agent_online(_utc(agent.last_seen_at), now, offline_seconds),
        detail=True,
    )


def acknowledge_episode(session: Session, agent_id: str, episode_id: str) -> None:
    session.get(Agent, agent_id, with_for_update=True)
    episode = _get(session, agent_id, episode_id)
    if episode.acknowledged_at is None:
        episode.acknowledged_at = datetime.now(UTC)
        event(
            session, episode, "acknowledged", episode.acknowledged_at, {"recovery_confirmed": False}
        )
    session.commit()


def capture_command_result(
    session: Session, command: AgentCommand, status: str, data: dict, message: str | None
) -> None:
    episode_id = command.payload.get("episode_id")
    capture = session.get(EpisodeCapture, episode_id) if episode_id else None
    if capture is None:
        return
    capture.status = "accepted" if status == "acked" else "failed"
    capture.coverage = {**data, "message": message}
    episode = session.get(ClientEpisode, episode_id)
    recording = (
        session.get(DiagnosticRecording, capture.recording_id) if capture.recording_id else None
    )
    if status == "acked" and recording and recording.status == "completed":
        finalize_capture_coverage(session, recording)
    event(
        session,
        episode,
        "capture_accepted" if status == "acked" else "capture_failed",
        datetime.now(UTC),
        capture.coverage,
    )


def finalize_capture_coverage(session: Session, recording: DiagnosticRecording) -> None:
    for capture in session.scalars(
        select(EpisodeCapture).where(
            EpisodeCapture.recording_id == recording.id,
            EpisodeCapture.status.in_(("accepted", "partial", "complete")),
        )
    ).all():
        cycles = session.scalars(
            select(RecordingMetric)
            .where(
                RecordingMetric.recording_id == recording.id,
                RecordingMetric.metric == "sensor.collection_cycle",
                RecordingMetric.observed_at >= capture.requested_start,
                RecordingMetric.observed_at <= capture.requested_end,
            )
            .order_by(RecordingMetric.observed_at)
            .limit(20001)
        ).all()
        times = sorted({_utc(item.observed_at) for item in cycles})
        interval = max(
            (float(item.labels.get("configured_interval_seconds", 1)) for item in cycles), default=1
        )
        tolerance = max(3, interval * 3)
        gaps = sum(
            (later - earlier).total_seconds() > tolerance
            for earlier, later in zip(times, times[1:], strict=False)
        )
        complete = (
            bool(times)
            and len(cycles) <= 20000
            and gaps == 0
            and (times[0] - _utc(capture.requested_start)).total_seconds() <= tolerance
            and (_utc(capture.requested_end) - times[-1]).total_seconds() <= tolerance
            and recording.sync_status == "complete"
        )
        capture.status = "complete" if complete else "partial"
        capture.coverage = {
            **capture.coverage,
            "evidence_start": times[0].isoformat() if times else None,
            "evidence_end": times[-1].isoformat() if times else None,
            "cycle_samples": len(times),
            "gap_count": gaps,
            "collection_error_cycles": sum(
                bool(item.labels.get("collector_errors_count")) for item in cycles
            ),
            "window_complete": complete,
            "truncated": len(cycles) > 20000,
            "sync_status": recording.sync_status,
        }
