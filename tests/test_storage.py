import json

from wem.models.metrics import (
    ConnectivityMetrics,
    NetworkMetrics,
    SensorSnapshot,
    WifiDeltaMetrics,
    WifiMetrics,
)
from wem.storage.database import Database
from wem.storage.repository import SnapshotRepository


def test_snapshot_repository_save(
    tmp_path,
) -> None:
    database = Database(str(tmp_path / "test.db"))

    database.initialize()

    repository = SnapshotRepository(database)

    snapshot = SensorSnapshot.create(
        wifi=WifiMetrics(
            interface="wlp0s20f3",
            ssid="AeP",
            bssid="98:7e:ca:8a:3e:0e",
            signal_dbm=-64,
            signal_avg_dbm=-65,
        ),
        wifi_delta=WifiDeltaMetrics(
            interval_seconds=10,
            tx_retries_per_100_packets=12.5,
        ),
        network=NetworkMetrics(
            interface="wlp0s20f3",
            ipv4_address="192.168.15.13",
            prefix_length=24,
            gateway="192.168.15.1",
        ),
        connectivity=ConnectivityMetrics(
            gateway_reachable=True,
            gateway_latency_avg_ms=5.2,
            gateway_packet_loss_percent=0,
            internet_reachable=True,
            internet_latency_avg_ms=20.4,
            internet_packet_loss_percent=0,
            dns_success=True,
            dns_latency_ms=8.3,
            https_success=True,
            https_status_code=200,
            https_total_time_ms=120.4,
        ),
    )

    record = repository.save(snapshot)

    assert record.id is not None

    assert record.interface == "wlp0s20f3"
    assert record.ssid == "AeP"

    assert record.signal_dbm == -64

    assert record.gateway_latency_avg_ms == 5.2
    assert record.internet_latency_avg_ms == 20.4

    assert record.tx_retries_per_100_packets == 12.5

    saved_snapshot = json.loads(record.snapshot_json)

    assert saved_snapshot["wifi"]["ssid"] == "AeP"


def test_repository_latest(
    tmp_path,
) -> None:
    database = Database(str(tmp_path / "test.db"))

    database.initialize()

    repository = SnapshotRepository(database)

    for signal in [-60, -61, -62]:
        snapshot = SensorSnapshot.create(
            wifi=WifiMetrics(
                interface="wlp0s20f3",
                signal_dbm=signal,
            ),
            wifi_delta=None,
            network=NetworkMetrics(
                interface="wlp0s20f3",
            ),
            connectivity=ConnectivityMetrics(),
        )

        repository.save(snapshot)

    records = repository.latest(limit=2)

    assert len(records) == 2
