from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from wifi_server.analysis.client_detector import consume_snapshot
from wifi_server.config import ServerSettings
from wifi_server.db.experience_models import AgentExperienceMonitor
from wifi_server.db.models import Agent, AgentCurrentState
from wifi_server.monitor_schemas import (
    ClientDetectionResponse,
    DetectionFinding,
    ExperienceProfile,
    ExperienceProfileResponse,
    ExperienceProfileUpdate,
)
from wifi_server.schemas import AgentCurrentStateResponse
from wifi_server.services.agents import _current_state_response, is_agent_online
from wifi_server.services.client_experience import _utc, evaluate_client_experience


def _agent(session: Session, agent_id: str, *, lock: bool = False) -> Agent:
    agent = session.get(Agent, agent_id, with_for_update=lock)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    return agent


def applied_version(state: AgentCurrentStateResponse | None) -> str | None:
    meta = state.measurement_metadata.get("wifi.connected") if state else None
    return meta.profile_version if meta else None


def get_profile(session: Session, agent_id: str) -> ExperienceProfileResponse:
    _agent(session, agent_id)
    monitor = session.get(AgentExperienceMonitor, agent_id)
    current = session.get(AgentCurrentState, agent_id)
    return ExperienceProfileResponse(
        agent_id=agent_id,
        version=monitor.profile_version if monitor else None,
        applied_version=applied_version(_current_state_response(current) if current else None),
        profile=ExperienceProfile.model_validate(monitor.profile)
        if monitor
        else ExperienceProfile(),
    )


def update_profile(
    session: Session, agent_id: str, payload: ExperienceProfileUpdate
) -> ExperienceProfileResponse:
    _agent(session, agent_id, lock=True)
    monitor = session.get(AgentExperienceMonitor, agent_id)
    if payload.expected_version != (monitor.profile_version if monitor else None):
        raise HTTPException(409, "The profile changed. Reload it before saving.")
    profile = payload.profile.model_dump(mode="json")
    if monitor is None:
        monitor = AgentExperienceMonitor(agent_id=agent_id)
        session.add(monitor)
    if monitor.profile != profile:
        monitor.profile = profile
        monitor.profile_version = f"exp_{uuid4().hex}"
        monitor.detector_state = {}
        monitor.updated_at = datetime.now(UTC)
    session.commit()
    return get_profile(session, agent_id)


def desired_profile(session: Session, agent_id: str) -> dict | None:
    monitor = session.get(AgentExperienceMonitor, agent_id)
    return {"version": monitor.profile_version, "profile": monitor.profile} if monitor else None


def ingest_detection(session: Session, state: AgentCurrentStateResponse, now: datetime) -> None:
    # Agent row is held by the ingestion route; profile edits take the same lock.
    monitor = session.get(AgentExperienceMonitor, state.agent_id)
    if monitor is None:
        return
    profile = ExperienceProfile.model_validate(monitor.profile)
    if not profile.enabled:
        return
    experience = evaluate_client_experience(state.agent_id, state, online=True, now=now)
    monitor.detector_state = consume_snapshot(
        monitor.detector_state or {}, state, experience, profile, monitor.profile_version
    )
    monitor.updated_at = now


def evaluate_detection(
    agent_id: str,
    monitor: AgentExperienceMonitor | None,
    current: AgentCurrentStateResponse | None,
    *,
    online: bool,
    now: datetime,
) -> ClientDetectionResponse:
    profile = ExperienceProfile.model_validate(monitor.profile) if monitor else ExperienceProfile()
    version = monitor.profile_version if monitor else None
    applied = applied_version(current)
    experience = evaluate_client_experience(agent_id, current, online=online, now=now)
    available_domains = {
        domain.domain
        for domain in experience.domains
        if domain.status in {"observed_ok", "failure", "degraded"}
    }
    entries = (monitor.detector_state or {}).get("rules", {}) if monitor else {}
    findings = []
    for entry in entries.values():
        if "domain" not in entry:
            continue
        item = DetectionFinding.model_validate(entry)
        if (
            not online
            or applied != version
            or item.domain not in available_domains
            or not item.observed_at
            or (now - _utc(item.observed_at)).total_seconds() > 30
        ):
            item = item.model_copy(
                update={
                    "previous_status": item.status
                    if item.status != "unknown"
                    else item.previous_status,
                    "status": "unknown",
                    "evidence_gap": True,
                    "reason": "Fresh comparable evidence is unavailable. "
                    "An evidence gap does not confirm recovery.",
                }
            )
        findings.append(item)
    active = sum(item.status == "active" for item in findings)
    statuses = {item.status for item in findings}
    status = (
        "disabled"
        if not profile.enabled
        else "pending_profile"
        if version != applied
        else "active"
        if active
        else "recovering"
        if "recovering" in statuses
        else "candidate"
        if "candidate" in statuses
        else "unknown"
        if not findings or "unknown" in statuses
        else "observed_ok"
    )
    return ClientDetectionResponse(
        agent_id=agent_id,
        evaluated_at=now,
        profile_version=version,
        applied_version=applied,
        enabled=profile.enabled,
        status=status,
        active_count=active,
        findings=findings,
        limitations=[
            "Rules describe this client's observed tests, not all clients or a causal diagnosis.",
            "Current State ingestion can miss tests between publications and while the Server "
            "is unavailable; late uploads are not replayed here.",
            "Initial references use successful observations under configured objectives. "
            "A frozen reference can still reflect a suboptimal initial environment.",
            "This delivery stores current rule state and references. "
            "Episode history and automatic captures belong to P0.4.",
        ],
    )


def get_detection(
    session: Session, settings: ServerSettings, agent_id: str
) -> ClientDetectionResponse:
    agent = _agent(session, agent_id)
    monitor = session.get(AgentExperienceMonitor, agent_id)
    current = session.get(AgentCurrentState, agent_id)
    now = datetime.now(UTC)
    return evaluate_detection(
        agent_id,
        monitor,
        _current_state_response(current) if current else None,
        online=is_agent_online(_utc(agent.last_seen_at), now, settings.agent_offline_after_seconds),
        now=now,
    )
