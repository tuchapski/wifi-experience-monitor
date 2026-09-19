from datetime import datetime

from sqlalchemy import desc, select

from wem.models.metrics import IncidentEvent
from wem.storage.database import Database
from wem.storage.models import IncidentRecord


class IncidentRepository:
    def __init__(
        self,
        database: Database,
    ):
        self.database = database

    def process_event(
        self,
        event: IncidentEvent,
    ) -> IncidentRecord | None:
        if event.action == "opened":
            return self._open_incident(event)

        if event.action == "resolved":
            return self._resolve_incident(event)

        return None

    def _open_incident(
        self,
        event: IncidentEvent,
    ) -> IncidentRecord:
        existing = self.get_active_by_code(event.code)

        if existing is not None:
            return existing

        first_seen_at = datetime.fromisoformat(event.first_seen_at)

        if event.opened_at is None:
            raise ValueError("Opened incident requires opened_at")

        opened_at = datetime.fromisoformat(event.opened_at)

        record = IncidentRecord(
            code=event.code,
            domain=event.domain,
            severity=event.severity,
            message=event.message,
            status="active",
            first_seen_at=first_seen_at,
            opened_at=opened_at,
            resolved_at=None,
        )

        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        return record

    def _resolve_incident(
        self,
        event: IncidentEvent,
    ) -> IncidentRecord | None:
        if event.resolved_at is None:
            raise ValueError("Resolved incident requires resolved_at")

        resolved_at = datetime.fromisoformat(event.resolved_at)

        with self.database.session() as session:
            statement = (
                select(IncidentRecord)
                .where(
                    IncidentRecord.code == event.code,
                    IncidentRecord.status == "active",
                )
                .order_by(desc(IncidentRecord.opened_at))
                .limit(1)
            )

            record = session.scalar(statement)

            if record is None:
                return None

            record.status = "resolved"
            record.resolved_at = resolved_at

            session.commit()
            session.refresh(record)

            return record

    def get_active_by_code(
        self,
        code: str,
    ) -> IncidentRecord | None:
        with self.database.session() as session:
            statement = (
                select(IncidentRecord)
                .where(
                    IncidentRecord.code == code,
                    IncidentRecord.status == "active",
                )
                .order_by(desc(IncidentRecord.opened_at))
                .limit(1)
            )

            return session.scalar(statement)

    def active(
        self,
    ) -> list[IncidentRecord]:
        with self.database.session() as session:
            statement = (
                select(IncidentRecord)
                .where(IncidentRecord.status == "active")
                .order_by(desc(IncidentRecord.opened_at))
            )

            return list(session.scalars(statement))

    def history(
        self,
        limit: int = 100,
    ) -> list[IncidentRecord]:
        with self.database.session() as session:
            statement = select(IncidentRecord).order_by(desc(IncidentRecord.opened_at)).limit(limit)

            return list(session.scalars(statement))
