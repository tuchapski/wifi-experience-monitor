from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from wem.api.app import create_app
from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    NetworkMetrics,
    SensorHealthMetrics,
    SensorSnapshot,
    WifiMetrics,
)
from wem.storage.database import Database
from wem.storage.history import HistoryRepository
from wem.storage.models import SnapshotRecord
from wem.storage.repository import SnapshotRepository

START = datetime(2026, 9, 21, 12, tzinfo=UTC)


@pytest.fixture
def database(tmp_path):
    db = Database(str(tmp_path / "history.db"))
    db.initialize()
    return db


def add_samples(database, rows):
    with database.session() as session:
        session.add_all(
            [
                SnapshotRecord(
                    timestamp=(START + timedelta(seconds=seconds)).replace(tzinfo=None),
                    interface=interface,
                    signal_dbm=signal,
                    snapshot_json="{}",
                )
                for seconds, interface, signal in rows
            ]
        )
        session.commit()


def test_aggregation_is_filtered_and_preserves_nulls_and_extremes(database):
    add_samples(
        database,
        [
            (-1, "wlan0", -10),
            (1, "wlan0", -60),
            (2, "wlan0", -80),
            (3, "wlan0", None),
            (1, "wlan1", -20),
            (21, "wlan0", -50),
            (100, "wlan0", -10),
        ],
    )
    result = HistoryRepository(database).window("wlan0", START, START + timedelta(seconds=100), 10)
    assert result["total_samples"] == 4
    assert result["bucket_seconds"] == 10
    assert len(result["points"]) == 10
    first = result["points"][0]
    assert first["sample_count"] == 3
    assert first["metrics"]["signal_dbm"] == {"avg": -70, "min": -80, "max": -60, "count": 2}
    assert result["points"][1]["metrics"]["signal_dbm"]["avg"] is None
    assert result["points"][1]["sample_count"] == 0
    assert first["metrics"]["gateway_packet_loss_percent"]["avg"] is None


def test_all_samples_are_included_without_last_100_limit(database):
    add_samples(database, [(index, "wlan0", -60) for index in range(1205)])
    result = HistoryRepository(database).window("wlan0", START, START + timedelta(hours=1), 10)
    assert result["total_samples"] == 1205
    assert len(result["points"]) == 10


def test_saved_offset_timestamp_is_normalized_to_utc(database):
    snapshot = SensorSnapshot.create(
        health=SensorHealthMetrics("wlan0"),
        calibration=CalibrationResult("inconclusive", False),
        wifi=WifiMetrics("wlan0", signal_dbm=-60),
        network=NetworkMetrics("wlan0"),
        connectivity=ConnectivityMetrics(),
    )
    snapshot.timestamp = "2026-09-21T09:00:01-03:00"
    SnapshotRepository(database).save(snapshot)
    result = HistoryRepository(database).window("wlan0", START, START + timedelta(minutes=1))
    assert result["total_samples"] == 1
    assert result["start"].endswith("+00:00")


@pytest.mark.parametrize(
    "start,end",
    [
        (START, START),
        (START, START - timedelta(seconds=1)),
        (START, START + timedelta(days=8)),
        (START.replace(tzinfo=None), START + timedelta(hours=1)),
    ],
)
def test_invalid_ranges_rejected(database, start, end):
    with pytest.raises(ValueError):
        HistoryRepository(database).window("wlan0", start, end)


def test_api_history_works_while_sensor_stopped_and_lists_stored_interfaces(tmp_path):
    path = str(tmp_path / "api.db")
    db = Database(path)
    db.initialize()
    add_samples(db, [(1, "removed-usb-wifi", -60)])
    with TestClient(create_app(path)) as client:
        assert client.get("/sensor/status").json()["running"] is False
        assert client.get("/history/interfaces").json() == ["removed-usb-wifi"]
        params = {
            "interface": "removed-usb-wifi",
            "start": START.isoformat(),
            "end": (START + timedelta(minutes=1)).isoformat(),
        }
        response = client.get("/history/window", params=params)
        assert response.status_code == 200
        assert response.json()["total_samples"] == 1
        assert (
            client.get("/history/window", params={**params, "max_points": 5000}).status_code == 422
        )
        assert (
            client.get("/history/window", params={**params, "end": params["start"]}).status_code
            == 422
        )
        assert (
            client.get("/history/window", params={**params, "interface": "missing"}).json()[
                "total_samples"
            ]
            == 0
        )
