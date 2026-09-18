from fastapi.testclient import TestClient

from wem.api.app import create_app
from wem.models.metrics import (
    ConnectivityMetrics,
    NetworkMetrics,
    SensorSnapshot,
    WifiDeltaMetrics,
    WifiMetrics,
)
from wem.storage.database import Database
from wem.storage.repository import SnapshotRepository


def create_test_snapshot() -> SensorSnapshot:
    return SensorSnapshot.create(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            ssid="AeP",
            bssid="98:7e:ca:8a:3e:0e",
            signal_dbm=-64,
            signal_avg_dbm=-65,
        ),
        wifi_delta=WifiDeltaMetrics(
            interval_seconds=10.0,
            tx_retries_per_100_packets=8.5,
        ),
        network=NetworkMetrics(
            interface="wlp0s20f3",
            ipv4_address="192.168.15.13",
            prefix_length=24,
            gateway="192.168.15.1",
        ),
        connectivity=ConnectivityMetrics(
            gateway_reachable=True,
            gateway_latency_avg_ms=5.0,
            gateway_packet_loss_percent=0.0,
            internet_reachable=True,
            internet_latency_avg_ms=20.0,
            internet_packet_loss_percent=0.0,
            dns_success=True,
            dns_latency_ms=7.0,
            https_success=True,
            https_status_code=200,
            https_total_time_ms=120.0,
        ),
    )


def test_health_without_snapshots(
    tmp_path,
) -> None:
    database_path = str(tmp_path / "test.db")

    app = create_app(database_path)

    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "has_snapshots": False,
    }


def test_latest_snapshot(
    tmp_path,
) -> None:
    database_path = str(tmp_path / "test.db")

    database = Database(database_path)
    database.initialize()

    repository = SnapshotRepository(database)

    repository.save(create_test_snapshot())

    app = create_app(database_path)

    client = TestClient(app)

    response = client.get("/snapshot/latest")

    assert response.status_code == 200

    body = response.json()

    assert body["wifi"]["ssid"] == "AeP"
    assert body["wifi"]["signal_dbm"] == -64

    assert body["connectivity"]["gateway_latency_avg_ms"] == 5.0


def test_latest_snapshot_returns_404(
    tmp_path,
) -> None:
    database_path = str(tmp_path / "test.db")

    app = create_app(database_path)

    client = TestClient(app)

    response = client.get("/snapshot/latest")

    assert response.status_code == 404


def test_history(
    tmp_path,
) -> None:
    database_path = str(tmp_path / "test.db")

    database = Database(database_path)
    database.initialize()

    repository = SnapshotRepository(database)

    repository.save(create_test_snapshot())

    app = create_app(database_path)

    client = TestClient(app)

    response = client.get("/history?limit=10")

    assert response.status_code == 200

    records = response.json()

    assert len(records) == 1

    assert records[0]["ssid"] == "AeP"
    assert records[0]["signal_dbm"] == -64

    assert records[0]["tx_retries_per_100_packets"] == 8.5
