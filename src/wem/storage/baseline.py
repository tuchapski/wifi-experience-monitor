from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import desc, select

from wem.storage.database import Database
from wem.storage.models import SnapshotRecord

_METRIC_COLUMNS = {
    "signal_dbm": "signal_dbm",
    "tx_retries_per_100_packets": "tx_retries_per_100_packets",
    "gateway_latency_avg_ms": "gateway_latency_avg_ms",
    "internet_latency_avg_ms": "internet_latency_avg_ms",
    "dns_latency_ms": "dns_latency_ms",
    "https_total_time_ms": "https_total_time_ms",
}
_TEST_METRICS = {
    "gateway_latency_avg_ms": "gateway",
    "internet_latency_avg_ms": "internet",
    "dns_latency_ms": "dns",
    "https_total_time_ms": "https",
}


class BaselineRepository:
    """Read bounded reference samples for the same interface and SSID."""

    def __init__(self, database: Database):
        self.database = database

    def reference_values(
        self,
        *,
        interface: str,
        ssid: str | None,
        before: datetime,
        lookback_hours: int,
        max_samples: int,
    ) -> dict[str, list[float]]:
        keys = [*_METRIC_COLUMNS, "connection_cycle_p95_ms"]
        values: dict[str, list[float]] = {key: [] for key in keys}
        if ssid is None:
            return values

        before_utc = self._utc(before)
        cutoff = before_utc - timedelta(hours=lookback_hours)
        query_limit = min(max_samples * 4, 20000)
        statement = (
            select(SnapshotRecord)
            .where(
                SnapshotRecord.interface == interface,
                SnapshotRecord.ssid == ssid,
                SnapshotRecord.timestamp >= cutoff.replace(tzinfo=None),
                SnapshotRecord.timestamp < before_utc.replace(tzinfo=None),
            )
            .order_by(desc(SnapshotRecord.timestamp))
            .limit(query_limit)
        )

        with self.database.session() as session:
            rows = list(session.scalars(statement))

        for row in rows:
            payload = self._payload(row.snapshot_json)
            for key, column in _METRIC_COLUMNS.items():
                if len(values[key]) >= max_samples:
                    continue
                test_name = _TEST_METRICS.get(key)
                if test_name is not None and not self._test_is_fresh(payload, test_name):
                    continue
                numeric = self._numeric(getattr(row, column))
                if numeric is not None:
                    values[key].append(numeric)

            if len(values["connection_cycle_p95_ms"]) < max_samples:
                p95 = self._fresh_cycle_p95(payload)
                if p95 is not None:
                    values["connection_cycle_p95_ms"].append(p95)

            if all(len(items) >= max_samples for items in values.values()):
                break

        for items in values.values():
            items.reverse()
        return values

    @staticmethod
    def _payload(raw: str) -> dict[str, object]:
        try:
            loaded = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}

    @staticmethod
    def _test_is_fresh(payload: dict[str, object], name: str) -> bool:
        connectivity = payload.get("connectivity")
        if not isinstance(connectivity, dict):
            return True
        tests = connectivity.get("tests")
        if not isinstance(tests, dict):
            return True
        outcome = tests.get(name)
        if not isinstance(outcome, dict):
            return True
        return outcome.get("fresh") is not False

    @classmethod
    def _fresh_cycle_p95(cls, payload: dict[str, object]) -> float | None:
        slo = payload.get("connection_cycle_slo")
        if not isinstance(slo, dict):
            return None
        if slo.get("fresh") is not True or slo.get("status") == "insufficient_data":
            return None
        return cls._numeric(slo.get("p95_ms"))

    @staticmethod
    def _numeric(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
