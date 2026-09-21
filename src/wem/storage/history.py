"""Bounded, time-bucketed history queries over the existing SQLite schema."""

import json
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, cast, func, select

from wem.storage.database import Database
from wem.storage.models import SnapshotRecord

METRICS = (
    "signal_dbm",
    "gateway_latency_avg_ms",
    "internet_latency_avg_ms",
    "dns_latency_ms",
    "https_total_time_ms",
    "gateway_packet_loss_percent",
    "internet_packet_loss_percent",
    "tx_retries_per_100_packets",
)


class HistoryRepository:
    def __init__(self, database: Database):
        self.database = database

    def interfaces(self) -> list[str]:
        statement = select(SnapshotRecord.interface).distinct().order_by(SnapshotRecord.interface)
        with self.database.session() as session:
            return list(session.scalars(statement))

    def window(self, interface: str, start: datetime, end: datetime, max_points: int = 600):
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Start and end must include a timezone.")
        start = start.astimezone(UTC).replace(microsecond=0)
        end = end.astimezone(UTC).replace(microsecond=0)
        duration = (end - start).total_seconds()
        if not 0 < duration <= 7 * 24 * 3600:
            raise ValueError("Choose a positive time range of at most seven days.")
        if not 10 <= max_points <= 1200:
            raise ValueError("max_points must be between 10 and 1200.")
        seconds = max(1, math.ceil(duration / max_points))
        bucket = cast(
            (cast(func.strftime("%s", SnapshotRecord.timestamp), Integer) - int(start.timestamp()))
            / seconds,
            Integer,
        )
        aggregates = [bucket.label("bucket"), func.count().label("samples")]
        for name in METRICS:
            column = getattr(SnapshotRecord, name)
            aggregates.extend(
                [
                    func.avg(column).label(f"{name}_avg"),
                    func.min(column).label(f"{name}_min"),
                    func.max(column).label(f"{name}_max"),
                    func.count(column).label(f"{name}_count"),
                ]
            )
        statement = (
            select(*aggregates)
            .where(
                SnapshotRecord.interface == interface,
                SnapshotRecord.timestamp >= start.replace(tzinfo=None),
                SnapshotRecord.timestamp < end.replace(tzinfo=None),
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        with self.database.session() as session:
            rows = {row["bucket"]: row for row in session.execute(statement).mappings()}
            event_rows = session.execute(
                select(SnapshotRecord.timestamp, SnapshotRecord.snapshot_json)
                .where(
                    SnapshotRecord.interface == interface,
                    SnapshotRecord.timestamp >= start.replace(tzinfo=None),
                    SnapshotRecord.timestamp < end.replace(tzinfo=None),
                )
                .order_by(SnapshotRecord.timestamp)
            ).all()

        events = []
        for timestamp, snapshot_json in event_rows:
            try:
                changes = json.loads(snapshot_json).get("environment_changes", [])
            except (TypeError, json.JSONDecodeError):
                changes = []
            for change in changes:
                events.append({"timestamp": timestamp.replace(tzinfo=UTC).isoformat(), **change})
        points = []
        for index in range(math.ceil(duration / seconds)):
            row = rows.get(index)
            metrics = {}
            for name in METRICS:
                metrics[name] = {
                    stat: row[f"{name}_{stat}"]
                    if row is not None
                    else (0 if stat == "count" else None)
                    for stat in ("avg", "min", "max", "count")
                }
            points.append(
                {
                    "timestamp": (start + timedelta(seconds=index * seconds)).isoformat(),
                    "sample_count": row["samples"] if row is not None else 0,
                    "metrics": metrics,
                }
            )
        return {
            "interface": interface,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "bucket_seconds": seconds,
            "total_samples": sum(point["sample_count"] for point in points),
            "points": points,
            "events": events,
        }
