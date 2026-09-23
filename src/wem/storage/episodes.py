import json
from datetime import UTC, datetime

from sqlalchemy import select

from wem.analysis.episodes import (
    CorrelationObservation,
    EpisodeIncident,
    ExperienceEpisodeEngine,
)
from wem.storage.database import Database
from wem.storage.models import IncidentRecord, SnapshotRecord


class EpisodeRepository:
    """Build derived experience episodes from incidents and stored correlation snapshots."""

    def __init__(self, database: Database, merge_gap_seconds: int = 120) -> None:
        self.database = database
        self.engine = ExperienceEpisodeEngine(merge_gap_seconds=merge_gap_seconds)

    def history(self, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        incident_limit = min(1000, max(200, limit * 20))
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(IncidentRecord)
                    .order_by(IncidentRecord.opened_at.desc())
                    .limit(incident_limit)
                )
            )

        if not records:
            return self.engine.build([], limit=limit)

        incidents = [
            EpisodeIncident(
                id=record.id,
                code=record.code,
                domain=record.domain,
                severity=record.severity,
                message=record.message,
                started_at=self._utc(record.opened_at),
                resolved_at=(
                    self._utc(record.resolved_at) if record.resolved_at is not None else None
                ),
            )
            for record in records
        ]
        earliest = min(item.started_at for item in incidents).replace(tzinfo=None)
        observations = self._correlations_since(earliest)
        return self.engine.build(incidents, observations, limit=limit)

    def _correlations_since(self, earliest: datetime) -> list[CorrelationObservation]:
        statement = (
            select(SnapshotRecord.timestamp, SnapshotRecord.snapshot_json)
            .where(
                SnapshotRecord.timestamp >= earliest,
                SnapshotRecord.overall_status.in_(("warning", "critical")),
            )
            .order_by(SnapshotRecord.timestamp)
        )
        observations: list[CorrelationObservation] = []
        with self.database.session() as session:
            rows = session.execute(statement).all()

        for timestamp, snapshot_json in rows:
            try:
                loaded = json.loads(snapshot_json)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(loaded, dict):
                continue
            correlation = loaded.get("correlation")
            if not isinstance(correlation, dict):
                continue
            status = correlation.get("status")
            primary_domain = correlation.get("primary_domain")
            if not isinstance(status, str):
                continue
            if primary_domain is not None and not isinstance(primary_domain, str):
                primary_domain = None
            observations.append(
                CorrelationObservation(
                    observed_at=self._utc(timestamp),
                    status=status,
                    primary_domain=primary_domain,
                )
            )
        return observations

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
