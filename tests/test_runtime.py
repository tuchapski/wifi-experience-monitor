from unittest.mock import patch

import pytest

from wem.models.metrics import (
    ConnectivityMetrics,
    NetworkMetrics,
    SensorHealthMetrics,
    WifiMetrics,
)
from wem.runtime.sensor import RuntimeConfig, SensorRuntime


@pytest.fixture(autouse=True)
def mock_health_collector():
    # Runtime unit tests must not inspect the machine's real wireless hardware.
    with patch("wem.runtime.sensor.SensorHealthCollector") as collector:
        collector.return_value.collect.return_value = SensorHealthMetrics(
            interface="wlp0s20f3",
            interface_exists=True,
            interface_up=True,
            wireless_interface=True,
            driver="iwlwifi",
        )
        collector.return_value.errors = []
        yield collector


class DummyRuntime(SensorRuntime):
    def on_snapshot(self, snapshot) -> None:
        pass


@patch("wem.runtime.sensor.ConnectivityTester")
@patch("wem.runtime.sensor.NetworkCollector")
@patch("wem.runtime.sensor.WifiCollector")
@patch("wem.runtime.sensor.time.monotonic")
def test_runtime_first_collection_has_no_delta(
    mock_monotonic,
    mock_wifi_collector,
    mock_network_collector,
    mock_connectivity_tester,
) -> None:
    mock_monotonic.return_value = 100.0

    wifi = WifiMetrics(
        interface="wlp0s20f3",
        bssid="98:7e:ca:8a:3e:0e",
        tx_packets=100,
        tx_retries=10,
    )

    network = NetworkMetrics(
        interface="wlp0s20f3",
        gateway="192.168.15.1",
    )

    connectivity = ConnectivityMetrics(
        gateway_reachable=True,
    )

    mock_wifi_collector.return_value.collect.return_value = wifi
    mock_wifi_collector.return_value.errors = []

    mock_network_collector.return_value.collect.return_value = network
    mock_network_collector.return_value.errors = []

    mock_connectivity_tester.return_value.run.return_value = connectivity
    mock_connectivity_tester.return_value.errors = []

    runtime = DummyRuntime(
        RuntimeConfig(
            interface="wlp0s20f3",
            interval_seconds=10.0,
        )
    )

    snapshot = runtime.collect_once()

    assert snapshot.wifi_delta is None
    assert snapshot.wifi is wifi
    assert snapshot.network is network
    assert snapshot.connectivity is connectivity


@patch("wem.runtime.sensor.ConnectivityTester")
@patch("wem.runtime.sensor.NetworkCollector")
@patch("wem.runtime.sensor.WifiCollector")
@patch("wem.runtime.sensor.time.monotonic")
def test_runtime_calculates_wifi_delta(
    mock_monotonic,
    mock_wifi_collector,
    mock_network_collector,
    mock_connectivity_tester,
) -> None:
    mock_monotonic.side_effect = [
        100.0,
        110.0,
    ]

    first_wifi = WifiMetrics(
        interface="wlp0s20f3",
        bssid="98:7e:ca:8a:3e:0e",
        tx_packets=100,
        tx_retries=10,
        tx_failed=0,
        rx_packets=200,
        rx_drop_misc=2,
    )

    second_wifi = WifiMetrics(
        interface="wlp0s20f3",
        bssid="98:7e:ca:8a:3e:0e",
        tx_packets=200,
        tx_retries=30,
        tx_failed=1,
        rx_packets=400,
        rx_drop_misc=4,
    )

    mock_wifi_collector.return_value.collect.side_effect = [
        first_wifi,
        second_wifi,
    ]

    mock_wifi_collector.return_value.errors = []

    mock_network_collector.return_value.collect.return_value = NetworkMetrics(
        interface="wlp0s20f3",
        gateway="192.168.15.1",
    )

    mock_network_collector.return_value.errors = []

    mock_connectivity_tester.return_value.run.return_value = ConnectivityMetrics()

    mock_connectivity_tester.return_value.errors = []

    runtime = DummyRuntime(
        RuntimeConfig(
            interface="wlp0s20f3",
        )
    )

    first = runtime.collect_once()
    second = runtime.collect_once()

    assert first.wifi_delta is None
    assert second.wifi_delta is not None

    assert second.wifi_delta.interval_seconds == 10.0
    assert second.wifi_delta.tx_packets_delta == 100
    assert second.wifi_delta.tx_retries_delta == 20
    assert second.wifi_delta.tx_failed_delta == 1

    assert second.wifi_delta.rx_packets_delta == 200
    assert second.wifi_delta.rx_drop_misc_delta == 2

    assert second.wifi_delta.tx_retries_per_100_packets == 20.0
