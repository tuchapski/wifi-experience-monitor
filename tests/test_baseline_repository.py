import json
from datetime import UTC, datetime, timedelta

from wem.storage.baseline import BaselineRepository
from wem.storage.database import Database
from wem.storage.models import SnapshotRecord

START = datetime(2026, 9, 22, 12, tzinfo=UTC)


def add_row(
    database: Database,
    seconds: int,
    *,
    ssid: str = "CORP",
    signal: int = -60,
    gateway_ms: float = 10.0,
    gateway_fresh: bool = True,
    cycle_p95: float | None = None,
) -> None:
    payload: dict[str, object] = {
        "connectivity": {"tests": {"gateway": {"fresh": gateway_fresh}}},
    }
    if cycle_p95 is not None:
        payload["connection_cycle_slo"] = {
            "fresh": True,
            "status": "healthy",
            "sample_count": 5,
            "p95_ms": cycle_p95,
        }
    with database.session() as session:
        session.add(
            SnapshotRecord(
                timestamp=(START + timedelta(seconds=seconds)).replace(tzinfo=None),
                interface="wlan0",
                ssid=ssid,
                signal_dbm=signal,
                gateway_latency_avg_ms=gateway_ms,
                snapshot_json=json.dumps(payload),
            )
        )
        session.commit()


def test_reference_is_same_ssid_before_current_and_respects_fresh_tests(tmp_path):
    database = Database(str(tmp_path / "baseline.db"))
    database.initialize()
    add_row(database, 1, signal=-61, gateway_ms=11)
    add_row(database, 2, signal=-62, gateway_ms=999, gateway_fresh=False)
    add_row(database, 3, ssid="GUEST", signal=-90, gateway_ms=200)
    add_row(database, 4, signal=-63, gateway_ms=12, cycle_p95=1200)
    add_row(database, 20, signal=-20, gateway_ms=1)

    values = BaselineRepository(database).reference_values(
        interface="wlan0",
        ssid="CORP",
        before=START + timedelta(seconds=10),
        lookback_hours=1,
        max_samples=10,
    )

    assert sorted(values["signal_dbm"]) == [-63.0, -62.0, -61.0]
    assert sorted(values["gateway_latency_avg_ms"]) == [11.0, 12.0]
    assert values["connection_cycle_p95_ms"] == [1200.0]
