"""Bounded, time-bucketed history queries over the existing SQLite schema."""

import json
import math
from datetime import UTC, datetime, timedelta
from typing import cast as typing_cast

from sqlalchemy import Integer, cast, func, select

from wem.analysis.application_availability import summarize_application_availability
from wem.analysis.connection_cycle_stats import summarize_connection_cycles
from wem.analysis.service_slo_stats import summarize_service_executions
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


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 3)


class HistoryRepository:
    def __init__(self, database: Database):
        self.database = database

    def interfaces(self) -> list[str]:
        statement = select(SnapshotRecord.interface).distinct().order_by(SnapshotRecord.interface)
        with self.database.session() as session:
            return list(session.scalars(statement))

    def window(
        self,
        interface: str,
        start: datetime,
        end: datetime,
        max_points: int = 600,
        include_comparison: bool = False,
    ) -> dict[str, object]:
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
            raw_statement = select(
                SnapshotRecord.timestamp,
                *(getattr(SnapshotRecord, name) for name in METRICS),
            ).where(
                SnapshotRecord.interface == interface,
                SnapshotRecord.timestamp >= start.replace(tzinfo=None),
                SnapshotRecord.timestamp < end.replace(tzinfo=None),
            )
            raw_rows = session.execute(raw_statement).all()
            event_rows = session.execute(
                select(SnapshotRecord.timestamp, SnapshotRecord.snapshot_json)
                .where(
                    SnapshotRecord.interface == interface,
                    SnapshotRecord.timestamp >= start.replace(tzinfo=None),
                    SnapshotRecord.timestamp < end.replace(tzinfo=None),
                )
                .order_by(SnapshotRecord.timestamp)
            ).all()

        values_by_bucket: dict[int, dict[str, list[float]]] = {}
        summary_values: dict[str, list[float]] = {name: [] for name in METRICS}
        start_naive = start.replace(tzinfo=None)
        for raw_row in raw_rows:
            timestamp = raw_row[0]
            bucket_index = int((timestamp - start_naive).total_seconds() // seconds)
            bucket_values = values_by_bucket.setdefault(bucket_index, {})
            for offset, name in enumerate(METRICS, start=1):
                value = raw_row[offset]
                if value is not None:
                    numeric_value = float(value)
                    bucket_values.setdefault(name, []).append(numeric_value)
                    summary_values[name].append(numeric_value)

        events: list[dict[str, object]] = []
        cycles_by_session: dict[str, dict[str, object]] = {}
        service_payloads: list[dict[str, object]] = []
        application_samples: list[tuple[datetime, dict[str, object]]] = []
        for timestamp, snapshot_json in event_rows:
            try:
                loaded = json.loads(snapshot_json)
                payload = loaded if isinstance(loaded, dict) else {}
                changes = payload.get("environment_changes", [])
            except (TypeError, json.JSONDecodeError):
                payload = {}
                changes = []
            service_payloads.append(payload)
            application_samples.append((timestamp.replace(tzinfo=UTC), payload))
            for change in changes:
                events.append({"timestamp": timestamp.replace(tzinfo=UTC).isoformat(), **change})
            cycle = payload.get("connection_cycle")
            if isinstance(cycle, dict):
                session_id = cycle.get("session_id")
                if isinstance(session_id, str) and session_id:
                    cycles_by_session[session_id] = cycle
        connection_cycles = sorted(
            cycles_by_session.values(),
            key=lambda cycle: str(cycle.get("last_observed_at", "")),
        )
        connection_cycle_summary = summarize_connection_cycles(connection_cycles)
        service_slo_summary = summarize_service_executions(service_payloads)
        application_availability = summarize_application_availability(
            application_samples,
            window_end=end,
        )
        points: list[dict[str, object]] = []
        for index in range(math.ceil(duration / seconds)):
            row = rows.get(index)
            metrics = {}
            for name in METRICS:
                values = values_by_bucket.get(index, {}).get(name, [])
                metrics[name] = {
                    stat: row[f"{name}_{stat}"]
                    if row is not None
                    else (0 if stat == "count" else None)
                    for stat in ("avg", "min", "max", "count")
                }
                metrics[name].update(
                    {
                        "p50": _percentile(values, 0.50),
                        "p95": _percentile(values, 0.95),
                        "p99": _percentile(values, 0.99),
                    }
                )
            points.append(
                {
                    "timestamp": (start + timedelta(seconds=index * seconds)).isoformat(),
                    "sample_count": row["samples"] if row is not None else 0,
                    "metrics": metrics,
                }
            )
        summary = self._summary(summary_values, len(raw_rows))
        result: dict[str, object] = {
            "interface": interface,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "bucket_seconds": seconds,
            "total_samples": sum(typing_cast(int, point["sample_count"]) for point in points),
            "points": points,
            "events": events,
            "connection_cycles": connection_cycles,
            "connection_cycle_summary": connection_cycle_summary,
            "service_slo_summary": service_slo_summary,
            "application_availability": application_availability,
            "summary": summary,
        }
        if include_comparison:
            previous = self.window(
                interface,
                start - timedelta(seconds=duration),
                start,
                max_points,
                include_comparison=False,
            )
            result["comparison"] = self.build_comparison(result, previous)
        return result

    @staticmethod
    def build_comparison(
        current: dict[str, object], reference: dict[str, object], reference_type: str = "previous"
    ) -> dict[str, object]:
        return {
            "current": current["summary"],
            "previous": reference["summary"],
            "previous_start": reference["start"],
            "previous_end": reference["end"],
            "reference_type": reference_type,
            "connection_cycles": {
                "current": current["connection_cycle_summary"],
                "previous": reference["connection_cycle_summary"],
            },
            "service_slo": {
                "current": current["service_slo_summary"],
                "previous": reference["service_slo_summary"],
            },
            "application_availability": {
                "current": current["application_availability"],
                "previous": reference["application_availability"],
            },
        }

    @staticmethod
    def _summary(
        values_by_metric: dict[str, list[float]],
        sample_count: int,
    ) -> dict[str, object]:
        metrics: dict[str, dict[str, float | int | None]] = {}
        for name, values in values_by_metric.items():
            metrics[name] = {
                "avg": round(sum(values) / len(values), 3) if values else None,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "count": len(values),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
                "p99": _percentile(values, 0.99),
            }
        return {"sample_count": sample_count, "metrics": metrics}
