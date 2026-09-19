import json
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from wem.storage.database import Database
from wem.storage.incidents import (
    IncidentRepository,
)
from wem.storage.models import (
    IncidentRecord,
    SnapshotRecord,
)
from wem.storage.repository import (
    SnapshotRepository,
)


def _record_to_summary(
    record: SnapshotRecord,
) -> dict[str, object]:
    return {
        "id": record.id,
        "timestamp": (record.timestamp.isoformat()),
        "interface": record.interface,
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
    duration_seconds: float | None = None

    end_time: datetime | None = record.resolved_at

    if end_time is not None:
        duration_seconds = (end_time - record.opened_at).total_seconds()

    return {
        "id": record.id,
        "code": record.code,
        "domain": record.domain,
        "severity": record.severity,
        "message": record.message,
        "status": record.status,
        "first_seen_at": (record.first_seen_at.isoformat()),
        "opened_at": (record.opened_at.isoformat()),
        "resolved_at": (record.resolved_at.isoformat() if record.resolved_at is not None else None),
        "duration_seconds": (duration_seconds),
    }


def create_app(
    database_path: str = "data/wem.db",
) -> FastAPI:
    database = Database(database_path)

    database.initialize()

    snapshot_repository = SnapshotRepository(database)

    incident_repository = IncidentRepository(database)

    app = FastAPI(
        title=("Wi-Fi Experience Monitor API"),
        description=("Local API for Wi-Fi and digital experience monitoring."),
        version="0.2.0",
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
            "active_incidents": (len(active_incidents)),
        }

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

    return app


database_path = os.environ.get(
    "WEM_DATABASE_PATH",
    "data/wem.db",
)

app = create_app(database_path)
