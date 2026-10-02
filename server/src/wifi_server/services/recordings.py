from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.db.models import (
    Agent,
    AgentRfBssObservation,
    AgentRfScan,
    DiagnosticRecording,
)
from wifi_server.db.project_models import DiagnosticProject, ProjectRun, ProjectRunRecording
from wifi_server.db.recording_models import (
    AgentCommand,
    RecordingBatch,
    RecordingEvent,
    RecordingMetric,
)
from wifi_server.recording_schemas import (
    AgentCommandAckRequest,
    RecordingBatchRequest,
    RecordingBatchResponse,
    RecordingEventResponse,
    RecordingManifestRequest,
    RecordingManifestResponse,
    RecordingMetricResponse,
    RecordingResponse,
    StartRecordingRequest,
)
from wifi_server.schemas import RfLatestScanResponse


def create_recording(
    session: Session,
    agent_id: str,
    request: StartRecordingRequest,
    *,
    commit: bool = True,
) -> RecordingResponse:
    agent = session.get(Agent, agent_id, with_for_update=True)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    active = session.scalar(
        select(DiagnosticRecording).where(
            DiagnosticRecording.agent_id == agent_id,
            DiagnosticRecording.status.in_(("created", "recording", "stopping")),
        )
    )
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent already has active recording {active.id}",
        )

    now = datetime.now(UTC)
    recording = DiagnosticRecording(
        id=f"rec_{uuid4().hex}",
        agent_id=agent_id,
        name=request.name,
        description=request.description,
        status="created",
        sync_status="pending",
        profile_id=request.profile_id,
        max_duration_minutes=request.max_duration_minutes,
        started_at=None,
        ended_at=None,
        site=request.site,
        location=request.location,
        agent_version=agent.agent_version,
        schema_version=1,
        metrics_count=0,
        events_count=0,
        tests_count=0,
        artifacts_count=0,
        created_at=now,
        updated_at=now,
    )
    session.add(recording)
    session.add(
        _command(
            agent_id,
            "recording.start",
            {
                "recording_id": recording.id,
                "profile_id": request.profile_id,
                "max_duration_minutes": request.max_duration_minutes,
            },
            now,
        )
    )
    if commit:
        session.commit()
    return _response(recording)


def request_stop_recording(session: Session, recording_id: str) -> RecordingResponse:
    recording = _get_recording(session, recording_id)
    if recording.status in {"completed", "failed", "cancelled"}:
        return _response(recording)
    if recording.status == "stopping":
        return _response(recording)

    now = datetime.now(UTC)
    recording.status = "stopping"
    recording.updated_at = now
    session.add(
        _command(
            recording.agent_id,
            "recording.stop",
            {"recording_id": recording.id},
            now,
        )
    )
    session.commit()
    return _response(recording)


def list_recordings(session: Session, agent_id: str) -> list[RecordingResponse]:
    if session.get(Agent, agent_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    recordings = session.execute(
        _recordings_with_projects()
        .where(DiagnosticRecording.agent_id == agent_id)
        .order_by(DiagnosticRecording.created_at.desc())
    ).all()
    return [
        _response(recording, project_id, project_name, project_run_id)
        for recording, project_id, project_name, project_run_id in recordings
    ]


def get_recording(session: Session, recording_id: str) -> RecordingResponse:
    row = session.execute(
        _recordings_with_projects().where(DiagnosticRecording.id == recording_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return _response(*row)


def get_recording_rf_scans(
    session: Session,
    recording_id: str,
    limit: int,
) -> list[RfLatestScanResponse]:
    _get_recording(session, recording_id)
    scans = list(
        session.scalars(
            select(AgentRfScan)
            .where(AgentRfScan.recording_id == recording_id)
            .order_by(AgentRfScan.observed_at.desc(), AgentRfScan.id.desc())
            .limit(limit)
        ).all()
    )
    scans.reverse()
    if not scans:
        return []

    scan_ids = [scan.id for scan in scans]
    bsses = session.scalars(
        select(AgentRfBssObservation)
        .where(AgentRfBssObservation.rf_scan_id.in_(scan_ids))
        .order_by(
            AgentRfBssObservation.rf_scan_id,
            AgentRfBssObservation.associated.desc(),
            AgentRfBssObservation.rssi_dbm.desc().nulls_last(),
            AgentRfBssObservation.bssid,
        )
    ).all()

    bsses_by_scan: dict[int, list[AgentRfBssObservation]] = {}
    for bss in bsses:
        bsses_by_scan.setdefault(bss.rf_scan_id, []).append(bss)

    return [
        RfLatestScanResponse(
            scan_id=scan.scan_id,
            sequence=scan.sequence,
            observed_at=scan.observed_at,
            interface=scan.interface,
            duration_ms=scan.duration_ms,
            received_at=scan.received_at,
            bsses=[
                {
                    "bssid": bss.bssid,
                    "ssid": bss.ssid,
                    "frequency_mhz": bss.frequency_mhz,
                    "channel": bss.channel,
                    "band": bss.band,
                    "rssi_dbm": bss.rssi_dbm,
                    "associated": bss.associated,
                    "channel_width_mhz": bss.channel_width_mhz,
                    "beacon_interval_tu": bss.beacon_interval_tu,
                    "capability": bss.capability,
                    "privacy": bss.privacy,
                    "security": bss.security,
                    "phy_capabilities": bss.phy_capabilities,
                    "bss_load_station_count": bss.bss_load_station_count,
                    "bss_load_channel_utilization_raw": bss.bss_load_channel_utilization_raw,
                    "last_seen_ms": bss.last_seen_ms,
                }
                for bss in bsses_by_scan.get(scan.id, [])
            ],
        )
        for scan in scans
    ]


def get_recording_metrics(
    session: Session,
    recording_id: str,
    metric: str | None,
    limit: int,
) -> list[RecordingMetricResponse]:
    _get_recording(session, recording_id)
    query = select(RecordingMetric).where(RecordingMetric.recording_id == recording_id)
    if metric:
        query = query.where(RecordingMetric.metric == metric)
    records = list(
        session.scalars(query.order_by(RecordingMetric.observed_at.desc()).limit(limit)).all()
    )
    records.reverse()
    return [
        RecordingMetricResponse(
            observed_at=record.observed_at,
            metric=record.metric,
            value=record.value,
            unit=record.unit,
            labels=record.labels,
            received_at=record.received_at,
        )
        for record in records
    ]


def get_recording_events(
    session: Session,
    recording_id: str,
    limit: int,
) -> list[RecordingEventResponse]:
    _get_recording(session, recording_id)
    records = list(
        session.scalars(
            select(RecordingEvent)
            .where(RecordingEvent.recording_id == recording_id)
            .order_by(RecordingEvent.observed_at.desc())
            .limit(limit)
        ).all()
    )
    records.reverse()
    return [
        RecordingEventResponse(
            observed_at=record.observed_at,
            event_type=record.event_type,
            severity=record.severity,
            data=record.data,
            received_at=record.received_at,
        )
        for record in records
    ]


def get_pending_commands(
    session: Session,
    agent_id: str,
    delivered_at: datetime,
) -> list[dict[str, object]]:
    commands = session.scalars(
        select(AgentCommand)
        .where(
            AgentCommand.agent_id == agent_id,
            AgentCommand.status.in_(("pending", "delivered")),
        )
        .order_by(AgentCommand.created_at)
        .limit(20)
    ).all()
    response: list[dict[str, object]] = []
    for command in commands:
        if command.status == "pending":
            command.status = "delivered"
            command.delivered_at = delivered_at
        response.append(
            {
                "id": command.id,
                "type": command.command_type,
                "payload": command.payload,
            }
        )
    return response


def acknowledge_command(
    session: Session,
    command: AgentCommand,
    request: AgentCommandAckRequest,
) -> None:
    session.get(Agent, command.agent_id, with_for_update=True)
    session.refresh(command)
    if command.status in {"acked", "failed"}:
        return

    now = datetime.now(UTC)
    command.status = request.status
    command.acked_at = now
    command.result = {**request.data, "message": request.message}

    recording_id = str(command.payload.get("recording_id", ""))
    recording = session.get(DiagnosticRecording, recording_id) if recording_id else None
    if recording is not None:
        if command.command_type == "recording.capture":
            from wifi_server.services.client_episodes import capture_command_result

            capture_command_result(session, command, request.status, request.data, request.message)
            if command.payload.get("mode") == "automatic":
                if request.status == "failed" and recording.status == "created":
                    recording.status = recording.sync_status = "failed"
                elif request.status == "acked":
                    if recording.status == "created":
                        recording.status = "recording"
                    recording.started_at = (
                        recording.started_at
                        or _datetime_from_data(request.data.get("started_at"))
                        or now
                    )
        elif request.status == "failed":
            recording.status = "failed"
            recording.sync_status = "failed"
        elif command.command_type == "recording.start":
            if recording.status not in {"stopping", "completed", "failed", "cancelled"}:
                recording.status = "recording"
            recording.started_at = (
                recording.started_at or _datetime_from_data(request.data.get("started_at")) or now
            )
        elif command.command_type == "recording.stop":
            recording.status = "completed"
            recording.ended_at = _datetime_from_data(request.data.get("ended_at")) or now
        recording.updated_at = now

    session.commit()


def ingest_recording_batch(
    session: Session,
    recording: DiagnosticRecording,
    request: RecordingBatchRequest,
) -> RecordingBatchResponse:
    existing = session.scalar(
        select(RecordingBatch).where(
            RecordingBatch.recording_id == recording.id,
            RecordingBatch.batch_id == request.batch_id,
        )
    )
    if existing is not None:
        return RecordingBatchResponse(
            batch_id=existing.batch_id,
            sequence=existing.sequence,
            status="already_accepted",
            metrics_received=existing.metric_count,
            events_received=existing.event_count,
        )

    sequence_owner = session.scalar(
        select(RecordingBatch).where(
            RecordingBatch.recording_id == recording.id,
            RecordingBatch.sequence == request.sequence,
        )
    )
    if sequence_owner is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recording sequence already belongs to another batch",
        )

    now = datetime.now(UTC)
    session.add(
        RecordingBatch(
            recording_id=recording.id,
            batch_id=request.batch_id,
            sequence=request.sequence,
            metric_count=len(request.metrics),
            event_count=len(request.events),
            received_at=now,
        )
    )
    for item in request.metrics:
        session.add(
            RecordingMetric(
                recording_id=recording.id,
                observed_at=item.observed_at,
                metric=item.metric,
                value=item.value,
                unit=item.unit,
                labels=item.labels,
                received_at=now,
            )
        )
    for item in request.events:
        session.add(
            RecordingEvent(
                recording_id=recording.id,
                observed_at=item.observed_at,
                event_type=item.event_type,
                severity=item.severity,
                data=item.data,
                received_at=now,
            )
        )

    recording.metrics_count += len(request.metrics)
    recording.events_count += len(request.events)
    recording.sync_status = "syncing"
    recording.updated_at = now
    session.commit()

    return RecordingBatchResponse(
        batch_id=request.batch_id,
        sequence=request.sequence,
        status="accepted",
        metrics_received=len(request.metrics),
        events_received=len(request.events),
    )


def finalize_manifest(
    session: Session,
    recording: DiagnosticRecording,
    request: RecordingManifestRequest,
    *,
    episode_coverage: bool = False,
) -> RecordingManifestResponse:
    sequences = list(
        session.scalars(
            select(RecordingBatch.sequence)
            .where(RecordingBatch.recording_id == recording.id)
            .order_by(RecordingBatch.sequence)
        ).all()
    )
    expected = set(range(1, request.batches_count + 1))
    missing = sorted(expected.difference(sequences))
    counts_match = (
        recording.metrics_count == request.metrics_count
        and recording.events_count == request.events_count
        and recording.tests_count == request.tests_count
        and recording.artifacts_count == request.artifacts_count
        and len(sequences) == request.batches_count
    )

    recording.status = "completed"
    recording.ended_at = request.ended_at
    recording.sync_status = "complete" if not missing and counts_match else "incomplete"
    recording.updated_at = datetime.now(UTC)
    if episode_coverage:
        from wifi_server.services.client_episodes import finalize_capture_coverage

        finalize_capture_coverage(session, recording)
    session.commit()

    return RecordingManifestResponse(
        recording_id=recording.id,
        status=recording.status,
        sync_status=recording.sync_status,
        missing_sequences=missing,
    )


def _command(
    agent_id: str,
    command_type: str,
    payload: dict[str, object],
    created_at: datetime,
) -> AgentCommand:
    return AgentCommand(
        id=f"cmd_{uuid4().hex}",
        agent_id=agent_id,
        command_type=command_type,
        payload=payload,
        status="pending",
        created_at=created_at,
        delivered_at=None,
        acked_at=None,
        result={},
    )


def _get_recording(session: Session, recording_id: str) -> DiagnosticRecording:
    recording = session.get(DiagnosticRecording, recording_id)
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    return recording


def _recordings_with_projects():
    return (
        select(
            DiagnosticRecording,
            ProjectRun.project_id,
            DiagnosticProject.name,
            ProjectRunRecording.run_id,
        )
        .outerjoin(ProjectRunRecording, ProjectRunRecording.recording_id == DiagnosticRecording.id)
        .outerjoin(ProjectRun, ProjectRun.id == ProjectRunRecording.run_id)
        .outerjoin(DiagnosticProject, DiagnosticProject.id == ProjectRun.project_id)
    )


def _response(
    recording: DiagnosticRecording,
    project_id: str | None = None,
    project_name: str | None = None,
    project_run_id: str | None = None,
) -> RecordingResponse:
    return RecordingResponse(
        id=recording.id,
        agent_id=recording.agent_id,
        project_id=project_id,
        project_name=project_name,
        project_run_id=project_run_id,
        name=recording.name,
        description=recording.description,
        site=recording.site,
        location=recording.location,
        status=recording.status,
        sync_status=recording.sync_status,
        profile_id=recording.profile_id,
        max_duration_minutes=recording.max_duration_minutes,
        started_at=recording.started_at,
        ended_at=recording.ended_at,
        agent_version=recording.agent_version,
        schema_version=recording.schema_version,
        metrics_count=recording.metrics_count,
        events_count=recording.events_count,
        tests_count=recording.tests_count,
        artifacts_count=recording.artifacts_count,
        created_at=recording.created_at,
        updated_at=recording.updated_at,
    )


def _datetime_from_data(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
