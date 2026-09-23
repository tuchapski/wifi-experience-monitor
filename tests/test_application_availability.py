import json
from datetime import UTC, datetime, timedelta

from wem.analysis.application_availability import summarize_application_availability
from wem.storage.database import Database
from wem.storage.history import HistoryRepository
from wem.storage.models import SnapshotRecord

START = datetime(2026, 9, 22, 12, tzinfo=UTC)


def _payload(
    status: str,
    *,
    fresh: bool = True,
    name: str = "Portal",
    target: str = "https://portal.example.com/health",
) -> dict[str, object]:
    return {
        "connectivity": {
            "application_targets": {
                name: {
                    "name": name,
                    "kind": "http",
                    "target": target,
                    "port": None,
                    "status": status,
                    "fresh": fresh,
                }
            }
        }
    }


def test_availability_uses_only_fresh_definitive_executions_and_groups_outage() -> None:
    samples = [
        (START, _payload("passed")),
        (START + timedelta(seconds=10), _payload("failed")),
        (START + timedelta(seconds=20), _payload("error")),
        (START + timedelta(seconds=30), _payload("failed")),
        (START + timedelta(seconds=40), _payload("passed")),
        (START + timedelta(seconds=50), _payload("failed", fresh=False)),
    ]

    result = summarize_application_availability(
        samples,
        window_end=START + timedelta(seconds=60),
    )
    target = result["targets"][0]

    assert target["attempt_count"] == 5
    assert target["measurable_count"] == 4
    assert target["success_count"] == 2
    assert target["failure_count"] == 2
    assert target["measurement_error_count"] == 1
    assert target["availability_percent"] == 50.0
    assert target["outage_count"] == 1
    assert target["open_outage"] is False
    assert target["observed_outage_seconds"] == 30.0
    assert target["longest_observed_outage_seconds"] == 30.0
    assert target["outages"][0]["failure_count"] == 2
    assert target["outages"][0]["recovered"] is True


def test_open_outage_is_bounded_by_window_end_without_inventing_recovery() -> None:
    result = summarize_application_availability(
        [(START + timedelta(seconds=10), _payload("failed"))],
        window_end=START + timedelta(seconds=60),
    )
    target = result["targets"][0]
    outage = target["outages"][0]

    assert target["availability_percent"] == 0.0
    assert target["open_outage"] is True
    assert target["observed_outage_seconds"] == 50.0
    assert outage["ended_at"] is None
    assert outage["recovered"] is False


def test_reconfigured_target_with_same_name_is_accounted_separately() -> None:
    result = summarize_application_availability(
        [
            (START, _payload("passed", target="https://one.example.com")),
            (
                START + timedelta(seconds=10),
                _payload("failed", target="https://two.example.com"),
            ),
        ],
        window_end=START + timedelta(seconds=20),
    )

    assert result["target_count"] == 2
    assert {item["target"] for item in result["targets"]} == {
        "https://one.example.com",
        "https://two.example.com",
    }


def test_history_window_exposes_application_availability_and_previous_period(tmp_path) -> None:
    database = Database(str(tmp_path / "availability.db"))
    database.initialize()

    rows = [
        (-20, _payload("passed")),
        (-10, _payload("passed")),
        (10, _payload("passed")),
        (20, _payload("failed")),
        (30, _payload("passed")),
    ]
    with database.session() as session:
        session.add_all(
            [
                SnapshotRecord(
                    timestamp=(START + timedelta(seconds=offset)).replace(tzinfo=None),
                    interface="wlan0",
                    snapshot_json=json.dumps(payload),
                )
                for offset, payload in rows
            ]
        )
        session.commit()

    result = HistoryRepository(database).window(
        "wlan0",
        START,
        START + timedelta(seconds=60),
        max_points=10,
        include_comparison=True,
    )

    current = result["application_availability"]["targets"][0]
    previous = result["comparison"]["application_availability"]["previous"]["targets"][0]

    assert current["availability_percent"] == 66.667
    assert current["outage_count"] == 1
    assert current["observed_outage_seconds"] == 10.0
    assert previous["availability_percent"] == 100.0
