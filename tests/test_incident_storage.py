from wem.models.metrics import (
    IncidentEvent,
)
from wem.storage.database import (
    Database,
)
from wem.storage.incidents import (
    IncidentRepository,
)


def test_incident_open_and_resolve(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    database = Database(str(database_path))

    database.initialize()

    repository = IncidentRepository(database)

    opened = IncidentEvent(
        action="opened",
        code="WIFI_LOW_SIGNAL",
        domain="wifi",
        severity="warning",
        message="Low Wi-Fi signal",
        first_seen_at=("2026-09-18T10:00:00+00:00"),
        opened_at=("2026-09-18T10:00:10+00:00"),
        resolved_at=None,
    )

    repository.process_event(opened)

    active = repository.active()

    assert len(active) == 1

    assert active[0].code == "WIFI_LOW_SIGNAL"

    assert active[0].status == "active"

    resolved = IncidentEvent(
        action="resolved",
        code="WIFI_LOW_SIGNAL",
        domain="wifi",
        severity="warning",
        message="Low Wi-Fi signal",
        first_seen_at=("2026-09-18T10:00:00+00:00"),
        opened_at=("2026-09-18T10:00:10+00:00"),
        resolved_at=("2026-09-18T10:01:00+00:00"),
    )

    repository.process_event(resolved)

    active = repository.active()

    assert active == []

    history = repository.history()

    assert len(history) == 1

    assert history[0].status == "resolved"

    assert history[0].resolved_at is not None


def test_duplicate_open_is_ignored(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    database = Database(str(database_path))

    database.initialize()

    repository = IncidentRepository(database)

    event = IncidentEvent(
        action="opened",
        code="DNS_FAILURE",
        domain="dns",
        severity="critical",
        message="DNS resolution failed",
        first_seen_at=("2026-09-18T10:00:00+00:00"),
        opened_at=("2026-09-18T10:00:05+00:00"),
        resolved_at=None,
    )

    repository.process_event(event)

    repository.process_event(event)

    history = repository.history()

    assert len(history) == 1


def test_clear_history_removes_ended_incidents_but_preserves_open_intervals(
    tmp_path,
) -> None:
    database = Database(str(tmp_path / "clear.db"))
    database.initialize()
    repository = IncidentRepository(database)

    repository.process_event(
        IncidentEvent(
            action="opened",
            code="WIFI_LOW_SIGNAL",
            domain="wifi",
            severity="warning",
            message="Low signal",
            first_seen_at="2026-09-18T10:00:00+00:00",
            opened_at="2026-09-18T10:00:10+00:00",
            resolved_at=None,
        )
    )
    repository.process_event(
        IncidentEvent(
            action="resolved",
            code="WIFI_LOW_SIGNAL",
            domain="wifi",
            severity="warning",
            message="Low signal",
            first_seen_at="2026-09-18T10:00:00+00:00",
            opened_at="2026-09-18T10:00:10+00:00",
            resolved_at="2026-09-18T10:01:00+00:00",
        )
    )
    repository.process_event(
        IncidentEvent(
            action="opened",
            code="DNS_FAILURE",
            domain="dns",
            severity="critical",
            message="DNS failed",
            first_seen_at="2026-09-18T10:02:00+00:00",
            opened_at="2026-09-18T10:02:10+00:00",
            resolved_at=None,
        )
    )

    assert repository.clear_history() == 1
    assert [record.code for record in repository.history()] == ["DNS_FAILURE"]
    assert [record.code for record in repository.active()] == ["DNS_FAILURE"]
