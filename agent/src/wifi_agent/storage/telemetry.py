import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from wifi_agent.processors.telemetry import TelemetryPoint


@dataclass(frozen=True, slots=True)
class PendingTelemetryBatch:
    batch_id: str
    sequence: int
    created_at: datetime
    items: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "sequence": self.sequence,
            "items": self.items,
        }


class TelemetrySpool:
    """Durable SQLite outbox for rolling telemetry batches."""

    def __init__(self, database_path: Path):
        self.database_path = database_path

    def initialize(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    next_sequence INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO telemetry_meta (singleton, next_sequence)
                VALUES (1, 1)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_batches (
                    batch_id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_telemetry_batches_sequence
                ON telemetry_batches (sequence)
                """
            )
            connection.commit()

    def enqueue(
        self,
        points: list[TelemetryPoint],
        created_at: datetime,
    ) -> PendingTelemetryBatch | None:
        if not points:
            return None

        batch_id = f"tb_{uuid4().hex}"
        items = [point.to_payload() for point in points]
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT next_sequence FROM telemetry_meta WHERE singleton = 1"
            ).fetchone()
            if row is None:
                raise RuntimeError("telemetry sequence metadata is missing")
            sequence = int(row[0])
            connection.execute(
                "UPDATE telemetry_meta SET next_sequence = ? WHERE singleton = 1",
                (sequence + 1,),
            )
            connection.execute(
                """
                INSERT INTO telemetry_batches (
                    batch_id,
                    sequence,
                    created_at,
                    payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (batch_id, sequence, created_at.isoformat(), json.dumps(items)),
            )
            connection.commit()

        return PendingTelemetryBatch(
            batch_id=batch_id,
            sequence=sequence,
            created_at=created_at,
            items=items,
        )

    def pending(self, limit: int = 20) -> list[PendingTelemetryBatch]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT batch_id, sequence, created_at, payload_json
                FROM telemetry_batches
                ORDER BY sequence
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            PendingTelemetryBatch(
                batch_id=row[0],
                sequence=int(row[1]),
                created_at=datetime.fromisoformat(row[2]),
                items=json.loads(row[3]),
            )
            for row in rows
        ]

    def acknowledge(self, batch_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM telemetry_batches WHERE batch_id = ?", (batch_id,))
            connection.commit()

    def prune_before(self, cutoff: datetime) -> int:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "DELETE FROM telemetry_batches WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            connection.commit()
            return cursor.rowcount

    def pending_count(self) -> int:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM telemetry_batches").fetchone()
        return int(row[0]) if row else 0
