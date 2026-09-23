from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PendingRecordingBatch:
    batch_id: str
    recording_id: str
    sequence: int
    created_at: datetime
    metrics: list[dict[str, Any]]
    events: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "sequence": self.sequence,
            "metrics": self.metrics,
            "events": self.events,
        }


@dataclass(frozen=True, slots=True)
class LocalRecording:
    recording_id: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    next_sequence: int
    metrics_count: int
    events_count: int
    manifest_pending: bool

    @property
    def batches_count(self) -> int:
        return max(0, self.next_sequence - 1)

    def manifest_payload(self) -> dict[str, Any]:
        if self.ended_at is None:
            raise RuntimeError("completed recording is missing ended_at")
        return {
            "ended_at": self.ended_at.isoformat(),
            "batches_count": self.batches_count,
            "metrics_count": self.metrics_count,
            "events_count": self.events_count,
            "tests_count": 0,
            "artifacts_count": 0,
        }
