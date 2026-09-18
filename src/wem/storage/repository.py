import json
from datetime import datetime

from sqlalchemy import desc, select

from wem.models.metrics import SensorSnapshot
from wem.storage.database import Database
from wem.storage.models import SnapshotRecord


class SnapshotRepository:
    def __init__(
        self,
        database: Database,
    ):
        self.database = database

    def save(
        self,
        snapshot: SensorSnapshot,
    ) -> SnapshotRecord:
        timestamp = datetime.fromisoformat(snapshot.timestamp)

        wifi_delta = snapshot.wifi_delta

        record = SnapshotRecord(
            timestamp=timestamp,
            interface=snapshot.wifi.interface,
            ssid=snapshot.wifi.ssid,
            bssid=snapshot.wifi.bssid,
            signal_dbm=snapshot.wifi.signal_dbm,
            signal_avg_dbm=snapshot.wifi.signal_avg_dbm,
            gateway_latency_avg_ms=(snapshot.connectivity.gateway_latency_avg_ms),
            gateway_packet_loss_percent=(snapshot.connectivity.gateway_packet_loss_percent),
            internet_latency_avg_ms=(snapshot.connectivity.internet_latency_avg_ms),
            internet_packet_loss_percent=(snapshot.connectivity.internet_packet_loss_percent),
            dns_latency_ms=(snapshot.connectivity.dns_latency_ms),
            https_total_time_ms=(snapshot.connectivity.https_total_time_ms),
            tx_retries_per_100_packets=(
                wifi_delta.tx_retries_per_100_packets if wifi_delta is not None else None
            ),
            collector_errors=json.dumps(
                snapshot.collector_errors,
            ),
            snapshot_json=json.dumps(
                snapshot.to_dict(),
                ensure_ascii=False,
            ),
        )

        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        return record

    def latest(
        self,
        limit: int = 10,
    ) -> list[SnapshotRecord]:
        statement = select(SnapshotRecord).order_by(desc(SnapshotRecord.timestamp)).limit(limit)

        with self.database.session() as session:
            return list(session.scalars(statement))

    def latest_one(
        self,
    ) -> SnapshotRecord | None:
        records = self.latest(limit=1)

        if not records:
            return None

        return records[0]

    def history(
        self,
        limit: int = 100,
    ) -> list[SnapshotRecord]:
        return self.latest(limit=limit)
