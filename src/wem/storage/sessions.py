from datetime import UTC, datetime

from wem.storage.database import Database
from wem.storage.models import MonitoringSessionRecord


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class MonitoringSessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def start(
        self,
        *,
        interface: str,
        profile_id: int,
        profile_version_id: int,
    ) -> MonitoringSessionRecord:
        record = MonitoringSessionRecord(
            interface=interface,
            profile_id=profile_id,
            profile_version_id=profile_version_id,
            started_at=_utc_now(),
            ended_at=None,
            status="running",
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def finish(self, session_id: int, status: str) -> MonitoringSessionRecord | None:
        with self.database.session() as session:
            record = session.get(MonitoringSessionRecord, session_id)
            if record is None:
                return None
            record.status = status
            record.ended_at = _utc_now()
            session.commit()
            session.refresh(record)
            return record

    def get(self, session_id: int) -> MonitoringSessionRecord | None:
        with self.database.session() as session:
            return session.get(MonitoringSessionRecord, session_id)
