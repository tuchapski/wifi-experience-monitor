import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from wem.collectors.interfaces import (
    WirelessInterfaceDiscovery,
)
from wem.profiles.defaults import default_profile_config
from wem.profiles.models import TestProfileConfig
from wem.profiles.service import (
    ActiveProfileDisabledError,
    DuplicateProfileNameError,
    ProfileDisabledError,
    ProfileNotFoundError,
    ProfileService,
    ProfileVersionNotFoundError,
)
from wem.reports.html import render_html_report
from wem.runtime.controller import SensorController
from wem.storage.database import Database
from wem.storage.history import HistoryRepository
from wem.storage.incidents import IncidentRepository
from wem.storage.models import (
    IncidentRecord,
    SnapshotRecord,
    TestProfileRecord,
    TestProfileVersionRecord,
)
from wem.storage.repository import SnapshotRepository


class SensorConfigRequest(BaseModel):
    interface: str

    interval_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=3600.0,
    )


ProfileName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProfileName
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    configuration: TestProfileConfig = Field(default_factory=default_profile_config)


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProfileName | None = None
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    configuration: TestProfileConfig | None = None


def _record_to_summary(
    record: SnapshotRecord,
) -> dict[str, object]:
    return {
        "id": record.id,
        "timestamp": (record.timestamp.isoformat()),
        "interface": (record.interface),
        "ssid": record.ssid,
        "bssid": record.bssid,
        "signal_dbm": (record.signal_dbm),
        "signal_avg_dbm": (record.signal_avg_dbm),
        "gateway_latency_avg_ms": (record.gateway_latency_avg_ms),
        "gateway_packet_loss_percent": (record.gateway_packet_loss_percent),
        "internet_latency_avg_ms": (record.internet_latency_avg_ms),
        "internet_packet_loss_percent": (record.internet_packet_loss_percent),
        "dns_latency_ms": (record.dns_latency_ms),
        "https_total_time_ms": (record.https_total_time_ms),
        "tx_retries_per_100_packets": (record.tx_retries_per_100_packets),
        "overall_status": (record.overall_status),
        "probable_domain": (record.probable_domain),
    }


def _incident_to_dict(
    record: IncidentRecord,
) -> dict[str, object]:
    end_time = record.resolved_at or datetime.now(UTC).replace(tzinfo=None)
    duration_seconds = max(0.0, (end_time - record.opened_at).total_seconds())

    return {
        "id": record.id,
        "code": record.code,
        "domain": record.domain,
        "severity": record.severity,
        "message": record.message,
        "first_seen_at": (_incident_timestamp(record.first_seen_at)),
        "started_at": (_incident_timestamp(record.opened_at)),
        "ended_at": (
            _incident_timestamp(record.resolved_at) if record.resolved_at is not None else None
        ),
        "duration_seconds": duration_seconds,
        "is_open": record.resolved_at is None,
    }


def _incident_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _profile_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _profile_payload(
    profile: TestProfileRecord,
    version: TestProfileVersionRecord,
    *,
    include_configuration: bool = True,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "enabled": profile.enabled,
        "active": profile.active_version_id == version.id,
        "version": version.version,
        "version_id": version.id,
        "created_at": _profile_timestamp(profile.created_at),
        "updated_at": _profile_timestamp(profile.updated_at),
        "version_created_at": _profile_timestamp(version.created_at),
    }
    if include_configuration:
        result["configuration"] = ProfileService.configuration(version).model_dump(mode="json")
    return result


def _version_payload(
    profile: TestProfileRecord,
    version: TestProfileVersionRecord,
) -> dict[str, object]:
    return {
        "id": version.id,
        "profile_id": profile.id,
        "version": version.version,
        "active": profile.active_version_id == version.id,
        "created_at": _profile_timestamp(version.created_at),
        "configuration": ProfileService.configuration(version).model_dump(mode="json"),
    }


def _raise_profile_http_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (ProfileNotFoundError, ProfileVersionNotFoundError)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(
        exc,
        (
            DuplicateProfileNameError,
            ProfileDisabledError,
            ActiveProfileDisabledError,
        ),
    ):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


def create_app(
    database_path: str = "data/wem.db",
) -> FastAPI:
    database = Database(database_path)

    database.initialize()

    snapshot_repository = SnapshotRepository(database)

    incident_repository = IncidentRepository(database)

    profile_service = ProfileService(database)

    sensor_controller = SensorController(database_path=database_path)

    interface_discovery = WirelessInterfaceDiscovery()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        sensor_controller.stop()

    app = FastAPI(
        lifespan=lifespan,
        title="Wi-Fi Experience Monitor API",
        description=("Local API for Wi-Fi and digital experience monitoring."),
        version="0.3.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "DELETE",
        ],
        allow_headers=[
            "*",
        ],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        latest = snapshot_repository.latest_one()

        active_incidents = incident_repository.active()

        return {
            "status": "ok",
            "database": "ok",
            "has_snapshots": (latest is not None),
            "active_incidents": len(active_incidents),
        }

    @app.get("/interfaces")
    def wireless_interfaces() -> list[dict[str, str | None]]:
        return interface_discovery.discover_dicts()

    @app.get("/profiles")
    def profiles() -> list[dict[str, object]]:
        return [
            _profile_payload(profile, version, include_configuration=False)
            for profile, version in profile_service.list_profiles()
        ]

    @app.post("/profiles", status_code=201)
    def create_profile(request: ProfileCreateRequest) -> dict[str, object]:
        try:
            profile, version = profile_service.create(
                name=request.name,
                description=request.description,
                enabled=request.enabled,
                config=request.configuration,
            )
        except Exception as exc:
            _raise_profile_http_error(exc)
        return _profile_payload(profile, version)

    @app.get("/profiles/active")
    def active_profile() -> dict[str, object]:
        try:
            profile, version = profile_service.active()
        except Exception as exc:
            _raise_profile_http_error(exc)
        return _profile_payload(profile, version)

    @app.get("/profiles/{profile_id}")
    def profile(profile_id: int) -> dict[str, object]:
        try:
            record, version = profile_service.get(profile_id)
        except Exception as exc:
            _raise_profile_http_error(exc)
        return _profile_payload(record, version)

    @app.put("/profiles/{profile_id}")
    def update_profile(
        profile_id: int,
        request: ProfileUpdateRequest,
    ) -> dict[str, object]:
        try:
            current, current_version = profile_service.get(profile_id)
            configuration = (
                request.configuration
                if request.configuration is not None
                else profile_service.configuration(current_version)
            )
            description = (
                request.description
                if "description" in request.model_fields_set
                else current.description
            )
            record, version = profile_service.update(
                profile_id,
                name=request.name if request.name is not None else current.name,
                description=description,
                enabled=request.enabled if request.enabled is not None else current.enabled,
                config=configuration,
            )
        except Exception as exc:
            _raise_profile_http_error(exc)
        return _profile_payload(record, version)

    @app.post("/profiles/{profile_id}/activate")
    def activate_profile(profile_id: int) -> dict[str, object]:
        try:
            record, version = profile_service.activate(profile_id)
        except Exception as exc:
            _raise_profile_http_error(exc)
        return _profile_payload(record, version)

    @app.get("/profiles/{profile_id}/versions")
    def profile_versions(profile_id: int) -> list[dict[str, object]]:
        try:
            record, _ = profile_service.get(profile_id)
            versions = profile_service.versions(profile_id)
        except Exception as exc:
            _raise_profile_http_error(exc)
        return [_version_payload(record, version) for version in versions]

    @app.get("/profiles/{profile_id}/versions/{version_number}")
    def profile_version(
        profile_id: int,
        version_number: int,
    ) -> dict[str, object]:
        try:
            record, _ = profile_service.get(profile_id)
            version = profile_service.version(profile_id, version_number)
        except Exception as exc:
            _raise_profile_http_error(exc)
        return _version_payload(record, version)

    @app.get("/config")
    def get_config() -> dict[str, object]:
        status = sensor_controller.status()

        return {
            "interface": (status["interface"]),
            "interval_seconds": (status["interval_seconds"]),
        }

    @app.put("/config")
    def configure_sensor(
        request: SensorConfigRequest,
    ) -> dict[str, object]:
        available_interfaces = {interface.name for interface in interface_discovery.discover()}

        if request.interface not in available_interfaces:
            raise HTTPException(
                status_code=400,
                detail=("Selected interface is not an available wireless interface."),
            )

        try:
            sensor_controller.configure(
                interface=request.interface,
                interval_seconds=(request.interval_seconds),
            )

        except RuntimeError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        return {
            "interface": (request.interface),
            "interval_seconds": (request.interval_seconds),
        }

    @app.post("/sensor/start")
    def start_sensor() -> dict[str, object]:
        try:
            sensor_controller.start()

        except RuntimeError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        return sensor_controller.status()

    @app.post("/sensor/stop")
    def stop_sensor() -> dict[str, object]:
        sensor_controller.stop()

        return sensor_controller.status()

    @app.get("/sensor/status")
    def sensor_status() -> dict[str, object]:
        return sensor_controller.status()

    @app.get("/snapshot/latest")
    def latest_snapshot() -> JSONResponse:
        record = snapshot_repository.latest_one()

        if record is None:
            raise HTTPException(
                status_code=404,
                detail=("No snapshots available"),
            )

        snapshot = json.loads(record.snapshot_json)

        return JSONResponse(content=snapshot)

    @app.get("/history/interfaces")
    def history_interfaces() -> list[str]:
        return HistoryRepository(database).interfaces()

    @app.get("/history/window")
    def history_window(
        start: datetime,
        end: datetime,
        interface: str = Query(min_length=1, max_length=64),
        max_points: int = Query(default=600, ge=10, le=1200),
        compare: bool = Query(default=True),
    ) -> dict[str, object]:
        try:
            return HistoryRepository(database).window(
                interface,
                start,
                end,
                max_points,
                include_comparison=compare,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/reports/html", response_class=HTMLResponse)
    def html_report(
        start: datetime,
        end: datetime,
        interface: str = Query(min_length=1, max_length=64),
    ) -> HTMLResponse:
        try:
            window = HistoryRepository(database).window(interface, start, end, max_points=600)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        start_utc = start.astimezone(UTC).replace(tzinfo=None)
        end_utc = end.astimezone(UTC).replace(tzinfo=None)
        incidents = [
            _incident_to_dict(record)
            for record in incident_repository.history(limit=1000)
            if record.opened_at < end_utc
            and (record.resolved_at is None or record.resolved_at >= start_utc)
        ]
        return HTMLResponse(
            content=render_html_report(window, incidents),
            headers={"Content-Disposition": 'inline; filename="wifi-experience-report.html"'},
        )

    @app.get("/history")
    def history(
        limit: int = Query(
            default=100,
            ge=1,
            le=1000,
        ),
    ) -> list[dict[str, object]]:
        records = snapshot_repository.history(limit=limit)

        return [_record_to_summary(record) for record in records]

    @app.get("/incidents/active")
    def active_incidents() -> list[dict[str, object]]:
        records = incident_repository.active()

        return [_incident_to_dict(record) for record in records]

    @app.get("/incidents/history")
    def incident_history(
        limit: int = Query(
            default=100,
            ge=1,
            le=1000,
        ),
    ) -> list[dict[str, object]]:
        records = incident_repository.history(limit=limit)

        return [_incident_to_dict(record) for record in records]

    @app.delete("/incidents/history")
    def clear_incident_history() -> dict[str, int]:
        return {"deleted": incident_repository.clear_history()}

    return app


database_path = os.environ.get(
    "WEM_DATABASE_PATH",
    "data/wem.db",
)

app = create_app(database_path)
