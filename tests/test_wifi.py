from unittest.mock import patch

from wem.collectors.command import CommandResult
from wem.collectors.wifi import WifiCollector

IW_INFO_OUTPUT = """
Interface wlp0s20f3
    ifindex 3
    wdev 0x1
    addr 80:38:fb:91:98:08
    ssid AeP
    type managed
    wiphy 0
    channel 52 (5260 MHz), width: 80 MHz, center1: 5290 MHz
    txpower 22.00 dBm
"""


IW_LINK_OUTPUT = """
Connected to 98:7e:ca:8a:3e:0e (on wlp0s20f3)
    SSID: AeP
    freq: 5260
    RX: 2531623 bytes (19490 packets)
    TX: 27384666 bytes (13466 packets)
    signal: -65 dBm
    rx bitrate: 351.0 MBit/s
    tx bitrate: 260.0 MBit/s
"""


IW_POWER_SAVE_OUTPUT = """
Power save: on
"""


IW_STATION_OUTPUT = """
Station 98:7e:ca:8a:3e:0e (on wlp0s20f3)
    inactive time:  36 ms
    rx bytes:       2531623
    rx packets:     19490
    tx bytes:       27384666
    tx packets:     13466
    tx retries:     7516
    tx failed:      1
    beacon loss:    0
    beacon rx:      2941
    rx drop misc:   136
    signal:         -65 [-65, -65] dBm
    signal avg:     -65 dBm
    beacon signal avg: -64 dBm
    tx bitrate:     260.0 MBit/s VHT-MCS 3 80MHz short GI VHT-NSS 2
    rx bitrate:     351.0 MBit/s VHT-MCS 4 80MHz VHT-NSS 2
    authorized:     yes
    authenticated:  yes
    associated:     yes
    preamble:       long
    WMM/WME:        yes
    MFP:            no
    TDLS peer:      no
    DTIM period:    2
    beacon interval:100
    short preamble: yes
    short slot time:yes
    connected time: 332 seconds
"""


def fake_run_command(command: list[str], timeout: float = 5.0) -> CommandResult:
    del timeout

    if command == ["iw", "dev", "wlp0s20f3", "info"]:
        return CommandResult(
            stdout=IW_INFO_OUTPUT,
            stderr="",
            returncode=0,
        )

    if command == ["iw", "dev", "wlp0s20f3", "link"]:
        return CommandResult(
            stdout=IW_LINK_OUTPUT,
            stderr="",
            returncode=0,
        )

    if command == [
        "iw",
        "dev",
        "wlp0s20f3",
        "get",
        "power_save",
    ]:
        return CommandResult(
            stdout=IW_POWER_SAVE_OUTPUT,
            stderr="",
            returncode=0,
        )

    if command == [
        "iw",
        "dev",
        "wlp0s20f3",
        "station",
        "dump",
    ]:
        return CommandResult(
            stdout=IW_STATION_OUTPUT,
            stderr="",
            returncode=0,
        )

    return CommandResult(
        stdout="",
        stderr="unexpected command",
        returncode=1,
    )


@patch(
    "wem.collectors.wifi.run_command",
    side_effect=fake_run_command,
)
def test_wifi_collector_parses_ax201_output(mock_run_command) -> None:
    collector = WifiCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.interface == "wlp0s20f3"

    assert metrics.ssid == "AeP"
    assert metrics.bssid == "98:7e:ca:8a:3e:0e"

    assert metrics.frequency_mhz == 5260
    assert metrics.channel == 52
    assert metrics.channel_width_mhz == 80

    assert metrics.signal_dbm == -65
    assert metrics.signal_avg_dbm == -65
    assert metrics.beacon_signal_avg_dbm == -64

    assert metrics.tx_power_dbm == 22.0

    assert metrics.tx_bitrate_mbps == 260.0
    assert metrics.rx_bitrate_mbps == 351.0

    assert metrics.tx_mcs == 3
    assert metrics.rx_mcs == 4

    assert metrics.tx_nss == 2
    assert metrics.rx_nss == 2

    assert metrics.tx_phy_mode == "VHT"
    assert metrics.rx_phy_mode == "VHT"

    assert metrics.tx_short_gi is True
    assert metrics.rx_short_gi is False

    assert metrics.tx_bytes == 27384666
    assert metrics.tx_packets == 13466
    assert metrics.tx_retries == 7516
    assert metrics.tx_failed == 1

    assert metrics.rx_bytes == 2531623
    assert metrics.rx_packets == 19490
    assert metrics.rx_drop_misc == 136

    assert metrics.beacon_rx == 2941
    assert metrics.beacon_loss == 0

    assert metrics.dtim_period == 2
    assert metrics.beacon_interval_ms == 100

    assert metrics.authorized is True
    assert metrics.authenticated is True
    assert metrics.associated is True

    assert metrics.wmm_enabled is True
    assert metrics.mfp_enabled is False

    assert metrics.connected_time_seconds == 332
    assert metrics.inactive_time_ms == 36

    assert metrics.power_save is True

    assert collector.errors == []

    assert mock_run_command.call_count == 4


@patch("wem.collectors.wifi.run_command")
def test_wifi_collector_handles_disconnected_interface(mock_run_command) -> None:
    def side_effect(command: list[str], timeout: float = 5.0) -> CommandResult:
        del timeout

        if command == ["iw", "dev", "wlp0s20f3", "info"]:
            return CommandResult(
                stdout=IW_INFO_OUTPUT,
                stderr="",
                returncode=0,
            )

        if command == ["iw", "dev", "wlp0s20f3", "link"]:
            return CommandResult(
                stdout="Not connected.",
                stderr="",
                returncode=0,
            )

        if command == [
            "iw",
            "dev",
            "wlp0s20f3",
            "get",
            "power_save",
        ]:
            return CommandResult(
                stdout="Power save: on",
                stderr="",
                returncode=0,
            )

        if command == [
            "iw",
            "dev",
            "wlp0s20f3",
            "station",
            "dump",
        ]:
            return CommandResult(
                stdout="",
                stderr="",
                returncode=0,
            )

        return CommandResult(
            stdout="",
            stderr="unexpected command",
            returncode=1,
        )

    mock_run_command.side_effect = side_effect

    collector = WifiCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.interface == "wlp0s20f3"
    assert metrics.ssid == "AeP"

    assert metrics.bssid is None
    assert metrics.signal_dbm is None

    assert metrics.tx_bitrate_mbps is None
    assert metrics.rx_bitrate_mbps is None

    assert metrics.associated is None

    assert collector.errors == ["wlp0s20f3 is not connected"]


@patch("wem.collectors.wifi.run_command")
def test_wifi_collector_handles_command_failures(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="",
        stderr="command failed",
        returncode=1,
    )

    collector = WifiCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.interface == "wlp0s20f3"

    assert metrics.ssid is None
    assert metrics.bssid is None
    assert metrics.signal_dbm is None

    assert metrics.tx_bitrate_mbps is None
    assert metrics.rx_bitrate_mbps is None

    assert collector.errors == [
        "iw info failed: command failed",
        "iw link failed: command failed",
        "power save check failed: command failed",
        "station dump failed: command failed",
    ]
