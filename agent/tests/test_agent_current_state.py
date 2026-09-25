from datetime import UTC, datetime
from unittest.mock import patch

from wifi_agent.collectors.command import CommandResult
from wifi_agent.collectors.network import NetworkStateCollector
from wifi_agent.collectors.wifi import WifiStateCollector
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.processors import StateProcessor
from wifi_agent.runtime.current_state import CurrentStateRuntime

IW_INFO = """
Interface wlp0s20f3
    ssid CORP
    type managed
    channel 44 (5220 MHz), width: 80 MHz, center1: 5210 MHz
"""

IW_LINK = """
Connected to aa:bb:cc:dd:ee:ff (on wlp0s20f3)
    SSID: CORP
    freq: 5220
    signal: -53 dBm
    rx bitrate: 648.0 MBit/s
    tx bitrate: 720.0 MBit/s
"""

IW_STATION = """
Station aa:bb:cc:dd:ee:ff (on wlp0s20f3)
    rx packets: 1000
    rx drop misc: 2
    tx packets: 900
    tx retries: 20
    tx failed: 1
    signal avg: -54 dBm
    tx bitrate: 720.0 MBit/s HE-MCS 7 80MHz HE-NSS 2
    rx bitrate: 648.0 MBit/s HE-MCS 6 80MHz HE-NSS 2
"""

IW_SURVEY = """
Survey data from wlp0s20f3
    frequency: 5220 MHz [in use]
    noise: -91 dBm
"""


def test_state_processor_builds_domain_snapshot() -> None:
    observed_at = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
    snapshot = StateProcessor().build(
        [
            Observation(
                "wifi",
                ObservationKind.STATE,
                "wifi.ssid",
                "CORP",
                observed_at=observed_at,
            ),
            Observation(
                "wifi",
                ObservationKind.GAUGE,
                "wifi.rssi_dbm",
                -53,
                "dBm",
                observed_at,
            ),
            Observation(
                "network",
                ObservationKind.STATE,
                "network.gateway",
                "192.168.1.1",
                observed_at=observed_at,
            ),
        ]
    )

    assert snapshot.wifi == {"ssid": "CORP", "rssi_dbm": -53}
    assert snapshot.network == {"gateway": "192.168.1.1"}


@patch("wifi_agent.collectors.wifi.run_command")
def test_wifi_collector_emits_current_state(mock_run_command) -> None:
    def side_effect(command: list[str], timeout: float = 5.0) -> CommandResult:
        del timeout
        if command[-1] == "info":
            return CommandResult(IW_INFO, "", 0)
        if command[-1] == "link":
            return CommandResult(IW_LINK, "", 0)
        if command[-2:] == ["station", "dump"]:
            return CommandResult(IW_STATION, "", 0)
        if command[-2:] == ["survey", "dump"]:
            return CommandResult(IW_SURVEY, "", 0)
        return CommandResult("", "unexpected", 1)

    mock_run_command.side_effect = side_effect
    values = {
        observation.metric: observation.value
        for observation in WifiStateCollector("wlp0s20f3").collect()
    }

    assert values["wifi.connected"] is True
    assert values["wifi.ssid"] == "CORP"
    assert values["wifi.bssid"] == "aa:bb:cc:dd:ee:ff"
    assert values["wifi.rssi_dbm"] == -53
    assert values["wifi.snr_db"] == 38.0
    assert values["wifi.tx_rate_mbps"] == 720.0
    assert values["wifi.tx_mcs"] == 7
    assert values["wifi.tx_nss"] == 2


@patch("wifi_agent.collectors.network.run_command")
def test_network_collector_emits_address_and_gateway(mock_run_command) -> None:
    def side_effect(command: list[str], timeout: float = 5.0) -> CommandResult:
        del timeout
        if "addr" in command:
            return CommandResult(
                "3: wlp0s20f3 inet 192.168.15.13/24 brd 192.168.15.255 scope global",
                "",
                0,
            )
        return CommandResult("default via 192.168.15.1 dev wlp0s20f3", "", 0)

    mock_run_command.side_effect = side_effect
    values = {
        observation.metric: observation.value
        for observation in NetworkStateCollector("wlp0s20f3").collect()
    }

    assert values["network.ipv4_address"] == "192.168.15.13"
    assert values["network.prefix_length"] == 24
    assert values["network.gateway"] == "192.168.15.1"


def test_current_snapshot_uses_fresh_counter_deltas_without_duplicating_recording() -> None:
    from datetime import timedelta

    runtime = CurrentStateRuntime("wlp0s20f3")
    start = datetime(2026, 9, 23, 22, 0, tzinfo=UTC)

    def cycle(at: datetime, packets: int, retries: int) -> list[Observation]:
        readings = (
            ("wifi.connected", True, ObservationKind.STATE),
            ("wifi.bssid", "aa:bb:cc:dd:ee:ff", ObservationKind.STATE),
            ("wifi.rssi_dbm", -60, ObservationKind.GAUGE),
            ("wifi.tx_packets", packets, ObservationKind.GAUGE),
            ("wifi.tx_retries", retries, ObservationKind.GAUGE),
            ("wifi.tx_failed", 0, ObservationKind.GAUGE),
        )
        return [
            Observation("wifi", kind, metric, value, observed_at=at)
            for metric, value, kind in readings
        ]

    with (
        patch.object(
            runtime.wifi,
            "collect",
            side_effect=[
                cycle(start, 100, 10),
                cycle(start + timedelta(seconds=1), 120, 14),
                cycle(start + timedelta(seconds=30), 140, 18),
            ],
        ),
        patch.object(runtime.network, "collect", return_value=[]),
    ):
        first = runtime.collect_cycle()
        second = runtime.collect_cycle()
        late = runtime.collect_cycle()

    assert "tx_retries_per_100_packets" not in first.snapshot.wifi
    assert second.snapshot.wifi["tx_retries_per_100_packets"] == 20
    assert all(item.metric != "wifi.tx_retries_per_100_packets" for item in second.observations)
    assert "tx_retries_per_100_packets" not in late.snapshot.wifi
