from fastapi.testclient import TestClient

from wem.api.app import create_app
from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    IncidentEvent,
    NetworkMetrics,
    SensorHealthMetrics,
    SensorSnapshot,
    WifiDeltaMetrics,
    WifiMetrics,
)
from wem.storage.database import Database
from wem.storage.incidents import IncidentRepository
from wem.storage.repository import SnapshotRepository


def create_test_snapshot() -> SensorSnapshot:
    return SensorSnapshot.create(
        health=SensorHealthMetrics(
            interface="wlp0s20f3",
            interface_exists=True,
            interface_up=True,
            wireless_interface=True,
            driver="iwlwifi",
            rfkill_soft_blocked=False,
            rfkill_hard_blocked=False,
        ),
        calibration=CalibrationResult(
            status="ok",
            calibrated=True,
        ),
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
        "active_incidents": 0,
    }


def test_health_reports_active_incidents(
    tmp_path,
) -> None:
    database_path = str(tmp_path / "test.db")

    app = create_app(database_path)

    client = TestClient(app)

    response = client.get("/health")

    body = response.json()

    assert body["active_incidents"] == 0


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


def test_incident_history_exposes_interval_and_can_be_cleared(tmp_path) -> None:
    database_path = str(tmp_path / "incidents.db")
    database = Database(database_path)
    database.initialize()
    repository = IncidentRepository(database)
    repository.process_event(
        IncidentEvent(
            action="opened",
            code="DNS_FAILURE",
            domain="dns",
            severity="critical",
            message="DNS failed",
            first_seen_at="2026-09-18T10:00:00+00:00",
            opened_at="2026-09-18T10:00:10+00:00",
            resolved_at=None,
        )
    )
    repository.process_event(
        IncidentEvent(
            action="resolved",
            code="DNS_FAILURE",
            domain="dns",
            severity="critical",
            message="DNS failed",
            first_seen_at="2026-09-18T10:00:00+00:00",
            opened_at="2026-09-18T10:00:10+00:00",
            resolved_at="2026-09-18T10:01:10+00:00",
        )
    )

    with TestClient(create_app(database_path)) as client:
        history = client.get("/incidents/history").json()
        assert history[0]["started_at"] == "2026-09-18T10:00:10+00:00"
        assert history[0]["ended_at"] == "2026-09-18T10:01:10+00:00"
        assert history[0]["duration_seconds"] == 60.0
        assert history[0]["is_open"] is False
        assert "status" not in history[0]

        response = client.delete("/incidents/history")
        assert response.status_code == 200
        assert response.json() == {"deleted": 1}
        assert client.get("/incidents/history").json() == []
