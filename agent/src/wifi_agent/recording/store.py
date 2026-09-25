import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from wifi_agent.recording.models import LocalRecording, PendingRecordingBatch


class RecordingStore:
    """Durable local recording metadata and outbox."""

    def __init__(self, database_path: Path):
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostic_recordings_local (
                    recording_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    next_sequence INTEGER NOT NULL,
                    metrics_count INTEGER NOT NULL,
                    events_count INTEGER NOT NULL,
                    manifest_pending INTEGER NOT NULL DEFAULT 0,
                    deadline_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recording_batches_local (
                    batch_id TEXT PRIMARY KEY,
                    recording_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    UNIQUE (recording_id, sequence)
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(diagnostic_recordings_local)")
            }
            if "deadline_at" not in columns:
                connection.execute(
                    "ALTER TABLE diagnostic_recordings_local ADD COLUMN deadline_at TEXT"
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_recording_batches_local_order
                ON recording_batches_local (recording_id, sequence)
                """
            )
            connection.commit()

    def start(
        self,
        recording_id: str,
        started_at: datetime,
        max_duration_minutes: int | None = None,
    ) -> LocalRecording:
        existing = self.get(recording_id)
        if existing is not None:
            return existing

        active = self.active()
        if active is not None and active.recording_id != recording_id:
            raise RuntimeError(f"recording {active.recording_id} is already active")

        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO diagnostic_recordings_local (
                    recording_id,
                    status,
                    started_at,
                    ended_at,
                    next_sequence,
                    metrics_count,
                    events_count,
                    manifest_pending,
                    deadline_at
                ) VALUES (?, 'recording', ?, NULL, 1, 0, 0, 0, ?)
                """,
                (
                    recording_id,
                    started_at.isoformat(),
                    (started_at + timedelta(minutes=max_duration_minutes)).isoformat()
                    if max_duration_minutes is not None
                    else None,
                ),
            )
            connection.commit()
        recording = self.get(recording_id)
        if recording is None:
            raise RuntimeError("recording was not persisted")
        return recording

    def stop(self, recording_id: str, ended_at: datetime) -> LocalRecording:
        recording = self.get(recording_id)
        if recording is None:
            raise RuntimeError(f"recording {recording_id} does not exist locally")
        if recording.status == "completed":
            return recording
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                UPDATE diagnostic_recordings_local
                SET status = 'completed', ended_at = ?, manifest_pending = 1
                WHERE recording_id = ?
                """,
                (ended_at.isoformat(), recording_id),
            )
            connection.commit()
        completed = self.get(recording_id)
        if completed is None:
            raise RuntimeError("recording disappeared after stop")
        return completed

    def active(self) -> LocalRecording | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT recording_id, status, started_at, ended_at, next_sequence,
                       metrics_count, events_count, manifest_pending, deadline_at
                FROM diagnostic_recordings_local
                WHERE status = 'recording'
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        return self._row_to_recording(row)

    def get(self, recording_id: str) -> LocalRecording | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT recording_id, status, started_at, ended_at, next_sequence,
                       metrics_count, events_count, manifest_pending, deadline_at
                FROM diagnostic_recordings_local
                WHERE recording_id = ?
                """,
                (recording_id,),
            ).fetchone()
        return self._row_to_recording(row)

    def enqueue(
        self,
        recording_id: str,
        metrics: list[dict[str, Any]],
        events: list[dict[str, Any]],
        created_at: datetime,
    ) -> PendingRecordingBatch | None:
        if not metrics and not events:
            return None

        batch_id = f"rb_{uuid4().hex}"
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, next_sequence
                FROM diagnostic_recordings_local
                WHERE recording_id = ?
                """,
                (recording_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"recording {recording_id} does not exist locally")
            if row[0] != "recording":
                connection.rollback()
                return None
            sequence = int(row[1])
            connection.execute(
                """
                INSERT INTO recording_batches_local (
                    batch_id, recording_id, sequence, created_at, metrics_json, events_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    recording_id,
                    sequence,
                    created_at.isoformat(),
                    json.dumps(metrics),
                    json.dumps(events),
                ),
            )
            connection.execute(
                """
                UPDATE diagnostic_recordings_local
                SET next_sequence = ?,
                    metrics_count = metrics_count + ?,
                    events_count = events_count + ?
                WHERE recording_id = ?
                """,
                (sequence + 1, len(metrics), len(events), recording_id),
            )
            connection.commit()

        return PendingRecordingBatch(
            batch_id=batch_id,
            recording_id=recording_id,
            sequence=sequence,
            created_at=created_at,
            metrics=metrics,
            events=events,
        )

    def pending(self, limit: int = 50) -> list[PendingRecordingBatch]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT batch_id, recording_id, sequence, created_at, metrics_json, events_json
                FROM recording_batches_local
                ORDER BY created_at, recording_id, sequence
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            PendingRecordingBatch(
                batch_id=row[0],
                recording_id=row[1],
                sequence=int(row[2]),
                created_at=datetime.fromisoformat(row[3]),
                metrics=json.loads(row[4]),
                events=json.loads(row[5]),
            )
            for row in rows
        ]

    def acknowledge_batch(self, batch_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "DELETE FROM recording_batches_local WHERE batch_id = ?",
                (batch_id,),
            )
            connection.commit()

    def recordings_waiting_for_manifest(self) -> list[LocalRecording]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT recording_id, status, started_at, ended_at, next_sequence,
                       metrics_count, events_count, manifest_pending, deadline_at
                FROM diagnostic_recordings_local
                WHERE status = 'completed' AND manifest_pending = 1
                ORDER BY ended_at
                """
            ).fetchall()
        return [recording for row in rows if (recording := self._row_to_recording(row))]

    def has_pending_batches(self, recording_id: str) -> bool:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM recording_batches_local
                WHERE recording_id = ?
                LIMIT 1
                """,
                (recording_id,),
            ).fetchone()
        return row is not None

    def acknowledge_manifest(self, recording_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                UPDATE diagnostic_recordings_local
                SET manifest_pending = 0
                WHERE recording_id = ?
                """,
                (recording_id,),
            )
            connection.commit()

    def pending_batch_count(self) -> int:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM recording_batches_local").fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _row_to_recording(row: tuple[Any, ...] | None) -> LocalRecording | None:
        if row is None:
            return None
        return LocalRecording(
            recording_id=row[0],
            status=row[1],
            started_at=datetime.fromisoformat(row[2]),
            ended_at=datetime.fromisoformat(row[3]) if row[3] else None,
            next_sequence=int(row[4]),
            metrics_count=int(row[5]),
            events_count=int(row[6]),
            manifest_pending=bool(row[7]),
            deadline_at=datetime.fromisoformat(row[8]) if row[8] else None,
        )
