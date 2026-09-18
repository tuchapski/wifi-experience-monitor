import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from wem.storage.database import Database
from wem.storage.models import SnapshotRecord
from wem.storage.repository import SnapshotRepository


def _record_to_summary(
    record: SnapshotRecord,
) -> dict[str, object]:
    return {
        "id": record.id,
        "timestamp": record.timestamp.isoformat(),
        "interface": record.interface,
        "ssid": record.ssid,
        "bssid": record.bssid,
        "signal_dbm": record.signal_dbm,
        "signal_avg_dbm": record.signal_avg_dbm,
        "gateway_latency_avg_ms": (record.gateway_latency_avg_ms),
        "gateway_packet_loss_percent": (record.gateway_packet_loss_percent),
        "internet_latency_avg_ms": (record.internet_latency_avg_ms),
        "internet_packet_loss_percent": (record.internet_packet_loss_percent),
        "dns_latency_ms": record.dns_latency_ms,
        "https_total_time_ms": (record.https_total_time_ms),
        "tx_retries_per_100_packets": (record.tx_retries_per_100_packets),
    }


def create_app(
    database_path: str = "data/wem.db",
) -> FastAPI:
    database = Database(database_path)
    database.initialize()

    repository = SnapshotRepository(database)

    app = FastAPI(
        title="Wi-Fi Experience Monitor API",
        description=("Local API for Wi-Fi and digital experience monitoring data."),
        version="0.1.0",
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        latest = repository.latest_one()

        return {
            "status": "ok",
            "database": "ok",
            "has_snapshots": latest is not None,
        }

    @app.get("/snapshot/latest")
    def latest_snapshot() -> JSONResponse:
        record = repository.latest_one()

        if record is None:
            raise HTTPException(
                status_code=404,
                detail="No snapshots available",
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
        records = repository.history(limit=limit)

        return [_record_to_summary(record) for record in records]

    return app


database_path = os.environ.get(
    "WEM_DATABASE_PATH",
    "data/wem.db",
)

app = create_app(database_path)
