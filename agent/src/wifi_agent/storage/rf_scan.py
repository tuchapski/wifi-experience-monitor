import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from wifi_agent.core.rf import BssObservation, RfScanResult


def _bss_payload(bss: BssObservation) -> dict[str, Any]:
    return {
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
        "security": list(bss.security),
        "phy_capabilities": list(bss.phy_capabilities),
        "bss_load_station_count": bss.bss_load_station_count,
        "bss_load_channel_utilization_raw": bss.bss_load_channel_utilization_raw,
        "last_seen_ms": bss.last_seen_ms,
    }


@dataclass(frozen=True, slots=True)
class PendingRfScan:
    scan_id: str
    sequence: int
    created_at: datetime
    observed_at: datetime
    interface: str
    duration_ms: float
    bsses: list[dict[str, Any]]
    recording_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "sequence": self.sequence,
            "recording_id": self.recording_id,
            "observed_at": self.observed_at.isoformat(),
            "interface": self.interface,
            "duration_ms": self.duration_ms,
            "bsses": self.bsses,
        }


class RfScanSpool:
    """Durable SQLite outbox for structured RF neighborhood scans."""

    def __init__(self, database_path: Path):
        self.database_path = database_path

    def initialize(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rf_scan_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    next_sequence INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO rf_scan_meta (singleton, next_sequence)
                VALUES (1, 1)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rf_scan_outbox (
                    scan_id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    recording_id TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(rf_scan_outbox)")}
            if "recording_id" not in columns:
                connection.execute("ALTER TABLE rf_scan_outbox ADD COLUMN recording_id TEXT")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_rf_scan_outbox_sequence
                ON rf_scan_outbox (sequence)
                """
            )
            connection.commit()

    def enqueue(self, result: RfScanResult) -> PendingRfScan | None:
        if not result.success:
            return None

        scan_id = f"rfs_{uuid4().hex}"
        created_at = datetime.now(UTC)
        payload = {
            "observed_at": result.observed_at.isoformat(),
            "interface": result.interface,
            "duration_ms": result.duration_ms,
            "bsses": [_bss_payload(bss) for bss in result.bsses],
        }

        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT next_sequence FROM rf_scan_meta WHERE singleton = 1"
            ).fetchone()
            if row is None:
                raise RuntimeError("RF scan sequence metadata is missing")
            sequence = int(row[0])
            connection.execute(
                "UPDATE rf_scan_meta SET next_sequence = ? WHERE singleton = 1",
                (sequence + 1,),
            )
            connection.execute(
                """
                INSERT INTO rf_scan_outbox (
                    scan_id,
                    sequence,
                    created_at,
                    recording_id,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    sequence,
                    created_at.isoformat(),
                    result.recording_id,
                    json.dumps(payload),
                ),
            )
            connection.commit()

        return PendingRfScan(
            scan_id=scan_id,
            sequence=sequence,
            created_at=created_at,
            observed_at=result.observed_at,
            interface=result.interface,
            duration_ms=result.duration_ms,
            bsses=payload["bsses"],
            recording_id=result.recording_id,
        )

    def pending(self, limit: int = 20) -> list[PendingRfScan]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT scan_id, sequence, created_at, recording_id, payload_json
                FROM rf_scan_outbox
                ORDER BY sequence
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        pending: list[PendingRfScan] = []
        for scan_id, sequence, created_at, recording_id, payload_json in rows:
            payload = json.loads(payload_json)
            pending.append(
                PendingRfScan(
                    scan_id=scan_id,
                    sequence=int(sequence),
                    created_at=datetime.fromisoformat(created_at),
                    observed_at=datetime.fromisoformat(payload["observed_at"]),
                    interface=payload["interface"],
                    duration_ms=float(payload["duration_ms"]),
                    bsses=list(payload["bsses"]),
                    recording_id=recording_id,
                )
            )
        return pending

    def acknowledge(self, scan_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM rf_scan_outbox WHERE scan_id = ?", (scan_id,))
            connection.commit()

    def prune_before(self, cutoff: datetime) -> int:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM rf_scan_outbox
                WHERE created_at < ? AND recording_id IS NULL
                """,
                (cutoff.isoformat(),),
            )
            connection.commit()
            return cursor.rowcount

    def pending_count(self) -> int:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM rf_scan_outbox").fetchone()
        return int(row[0]) if row else 0
