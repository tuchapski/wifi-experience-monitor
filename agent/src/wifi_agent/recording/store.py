import json
import sqlite3
from datetime import datetime, timedelta
from hashlib import sha256
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
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS experience_buffer (
                    cycle_time TEXT PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL,
                    payload_bytes INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS capture_commands (
                    command_id TEXT PRIMARY KEY, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS recording_fingerprints (
                    recording_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    PRIMARY KEY(recording_id, fingerprint));
            """)
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

        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._enqueue(connection, recording_id, metrics, events, created_at)

    def _enqueue(self, connection, recording_id, metrics, events, created_at):
        row = connection.execute(
            "SELECT status, next_sequence FROM diagnostic_recordings_local WHERE recording_id = ?",
            (recording_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"recording {recording_id} does not exist locally")
        if row[0] != "recording":
            return None
        unique = []
        for kind, items in (("metric", metrics), ("event", events)):
            selected = []
            for item in items:
                digest = sha256(
                    (kind + json.dumps(item, sort_keys=True, allow_nan=False)).encode()
                ).hexdigest()
                if connection.execute(
                    "INSERT OR IGNORE INTO recording_fingerprints VALUES (?, ?)",
                    (recording_id, digest),
                ).rowcount:
                    selected.append(item)
            unique.append(selected)
        metrics, events = unique
        if not metrics and not events:
            return None
        batch_id, sequence = f"rb_{uuid4().hex}", int(row[1])
        connection.execute(
            "INSERT INTO recording_batches_local VALUES (?, ?, ?, ?, ?, ?)",
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
            "UPDATE diagnostic_recordings_local SET next_sequence = ?, "
            "metrics_count = metrics_count + ?, events_count = events_count + ? "
            "WHERE recording_id = ?",
            (sequence + 1, len(metrics), len(events), recording_id),
        )
        return PendingRecordingBatch(
            batch_id=batch_id,
            recording_id=recording_id,
            sequence=sequence,
            created_at=created_at,
            metrics=metrics,
            events=events,
        )

    def buffer_cycle(self, scope, metrics, events, time, retention_seconds):
        payload = json.dumps({"metrics": metrics, "events": events}, allow_nan=False)
        size = len(payload.encode())
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "DELETE FROM experience_buffer WHERE scope != ? OR cycle_time < ?",
                (scope, (time - timedelta(seconds=retention_seconds)).isoformat()),
            )
            if size <= 1024 * 1024:
                connection.execute(
                    "INSERT OR REPLACE INTO experience_buffer VALUES (?, ?, ?, ?)",
                    (time.isoformat(), scope, payload, size),
                )
            # Bound both sample count and total serialized evidence, retaining newest cycles.
            rows = connection.execute(
                "SELECT cycle_time, payload_bytes FROM experience_buffer ORDER BY cycle_time DESC"
            ).fetchall()
            total = 0
            for index, (cycle_time, payload_bytes) in enumerate(rows):
                total += payload_bytes
                if index >= 2000 or total > 16 * 1024 * 1024:
                    connection.execute(
                        "DELETE FROM experience_buffer WHERE cycle_time = ?", (cycle_time,)
                    )

    def clear_buffer(self):
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM experience_buffer")

    def capture(self, command_id, recording_id, scope, start, end, now, mode):
        # Journal, local recording creation and buffered export commit together. An ack
        # failure or Agent restart can safely retry the same command without replay.
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            saved = connection.execute(
                "SELECT result FROM capture_commands WHERE command_id = ?", (command_id,)
            ).fetchone()
            if saved:
                return json.loads(saved[0])
            if end <= now:
                raise ValueError("Capture command expired; no recording was started")
            active = connection.execute(
                "SELECT recording_id FROM diagnostic_recordings_local WHERE status = 'recording'"
            ).fetchone()
            existing = connection.execute(
                "SELECT status, started_at FROM diagnostic_recordings_local WHERE recording_id = ?",
                (recording_id,),
            ).fetchone()
            if active and active[0] != recording_id:
                raise RuntimeError("Another individual recording is active")
            if existing and existing[0] != "recording":
                raise ValueError("Capture recording already ended; it will not be restarted")
            if mode == "reused" and not existing:
                raise ValueError("The recording to reuse is not active locally")
            rows = connection.execute(
                "SELECT cycle_time, payload FROM experience_buffer WHERE scope = ? "
                "AND cycle_time >= ? AND cycle_time <= ? ORDER BY cycle_time",
                (scope, start.isoformat(), min(now, end).isoformat()),
            ).fetchall()
            pending_bytes = connection.execute(
                "SELECT COALESCE(SUM(LENGTH(metrics_json) + LENGTH(events_json)), 0) "
                "FROM recording_batches_local"
            ).fetchone()[0]
            if pending_bytes > 128 * 1024 * 1024:
                raise RuntimeError("Capture deferred: local recording outbox exceeds 128 MiB")
            started_at = (
                datetime.fromisoformat(existing[1])
                if existing
                else datetime.fromisoformat(rows[0][0])
                if rows
                else now
            )
            if not existing:
                connection.execute(
                    "INSERT INTO diagnostic_recordings_local "
                    "VALUES (?, 'recording', ?, NULL, 1, 0, 0, 0, ?)",
                    (recording_id, started_at.isoformat(), end.isoformat()),
                )
            for time, payload in rows:
                cycle = json.loads(payload)
                self._enqueue(
                    connection,
                    recording_id,
                    cycle["metrics"],
                    cycle["events"],
                    datetime.fromisoformat(time),
                )
            result = {
                "recording_id": recording_id,
                "started_at": started_at.isoformat(),
                "buffer_start": rows[0][0] if rows else None,
                "buffer_end": rows[-1][0] if rows else None,
                "buffer_cycles": len(rows),
                "deadline_preserved": bool(existing),
                "pre_window_complete": bool(rows)
                and (datetime.fromisoformat(rows[0][0]) - start).total_seconds() <= 3,
                "requested_end": end.isoformat(),
            }
            connection.execute(
                "INSERT INTO capture_commands VALUES (?, ?)", (command_id, json.dumps(result))
            )
            return result

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
                "DELETE FROM recording_fingerprints WHERE recording_id = ?", (recording_id,)
            )
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
