from unittest.mock import patch

import pytest

from wem.analysis.wifi_delta import WifiDeltaAnalyzer
from wem.collectors.command import CommandResult
from wem.collectors.wifi import WifiCollector
from wem.models.metrics import WifiMetrics


@pytest.mark.parametrize(
    "line, mode, mcs, nss",
    [
        ("260.0 MBit/s VHT-MCS 3 80MHz short GI VHT-NSS 2", "VHT", 3, 2),
        ("573.5 MBit/s HE-MCS 11 40MHz HE-NSS 2 HE-GI 0", "HE", 11, 2),
        ("65.0 MBit/s MCS 7", "HT", 7, None),
        ("1200.0 MBit/s EHT-MCS 9 80MHz EHT-NSS 2", "EHT", 9, 2),
        ("6.0 MBit/s", None, None, None),
    ],
)
def test_reported_rate_metadata(line, mode, mcs, nss):
    metrics = WifiMetrics("wlan0", channel_width_mhz=160)
    WifiCollector("wlan0")._parse_bitrate(line, metrics, "tx")
    assert metrics.tx_phy_mode == mode
    assert metrics.tx_mcs == mcs
    assert metrics.tx_nss == nss
    assert metrics.channel_width_mhz == 160
    if mode in {"HE", "EHT", None}:
        assert metrics.tx_short_gi is None


def test_widths_are_independent():
    metrics = WifiMetrics("wlan0", channel_width_mhz=80)
    collector = WifiCollector("wlan0")
    collector._parse_bitrate("260.0 MBit/s VHT-MCS 3 80MHz VHT-NSS 2", metrics, "tx")
    collector._parse_bitrate("65.0 MBit/s VHT-MCS 3 20MHz VHT-NSS 1", metrics, "rx")
    assert metrics.channel_width_mhz == 80
    assert metrics.tx_channel_width_mhz == 80
    assert metrics.rx_channel_width_mhz == 20


def test_empty_station_preserves_link_data():
    with patch(
        "wem.collectors.wifi.run_command",
        side_effect=[
            CommandResult(
                "Connected to aa:bb:cc:dd:ee:ff (on wlan0)\n"
                "SSID: office\nfreq: 5260.0\nsignal: -65 dBm\n"
                "tx bitrate: 260.0 MBit/s VHT-MCS 3 80MHz VHT-NSS 2",
                "",
                0,
            ),
            CommandResult("", "", 0),
        ],
    ):
        collector = WifiCollector("wlan0")
        metrics = WifiMetrics("wlan0")
        collector._collect_link(metrics)
        collector._collect_station(metrics)
    assert metrics.associated is True
    assert metrics.ssid == "office"
    assert metrics.frequency_mhz == 5260
    assert metrics.signal_dbm == -65
    assert metrics.tx_mcs == 3
    assert metrics.tx_nss == 2


def test_partial_station_preserves_rssi_and_selects_associated_peer():
    metrics = WifiMetrics("wlan0", bssid="aa:bb:cc:dd:ee:ff", associated=True, signal_dbm=-65)
    output = (
        "Station 00:11:22:33:44:55 (on wlan0)\nsignal: -90 dBm\ntx packets: 900\n"
        "Station aa:bb:cc:dd:ee:ff (on wlan0)\ntx packets: 20\n"
    )
    with patch("wem.collectors.wifi.run_command", return_value=CommandResult(output, "", 0)):
        WifiCollector("wlan0")._collect_station(metrics)
    assert metrics.tx_packets == 20
    assert metrics.signal_dbm == -65
    assert metrics.associated is True


def test_decimal_frequency_in_interface_info():
    with patch(
        "wem.collectors.wifi.run_command",
        return_value=CommandResult(
            "channel 52 (5260.0 MHz), width: 80 MHz, center1: 5290 MHz", "", 0
        ),
    ):
        metrics = WifiMetrics("wlan0")
        WifiCollector("wlan0")._collect_info(metrics)
    assert metrics.channel == 52
    assert metrics.frequency_mhz == 5260
    assert metrics.channel_width_mhz == 80


@pytest.mark.parametrize("change", ["interface", "unknown_bssid", "disconnected", "reconnected"])
def test_incomparable_samples_do_not_produce_ratios(change):
    previous = WifiMetrics(
        "wlan0",
        bssid="aa:bb:cc:dd:ee:ff",
        connected_time_seconds=100,
        tx_packets=100,
        tx_retries=10,
    )
    current = WifiMetrics(
        "wlan0", bssid=previous.bssid, connected_time_seconds=105, tx_packets=200, tx_retries=20
    )
    if change == "interface":
        current.interface = "wlan1"
    elif change == "unknown_bssid":
        current.bssid = None
    elif change == "disconnected":
        current.associated = False
    else:
        current.connected_time_seconds = 1
    result = WifiDeltaAnalyzer().calculate(previous, current, 5)
    assert result.tx_retries_per_100_packets is None
    assert result.unavailable_reason


def test_no_traffic_is_not_zero_retry_rate():
    metrics = WifiMetrics("wlan0", bssid="aa:bb:cc:dd:ee:ff", tx_packets=100, tx_retries=20)
    result = WifiDeltaAnalyzer().calculate(metrics, metrics, 5)
    assert result.tx_packets_delta == 0
    assert result.tx_retries_per_100_packets is None


def test_retry_ratio_can_exceed_100():
    previous = WifiMetrics("wlan0", bssid="aa:bb:cc:dd:ee:ff", tx_packets=100, tx_retries=10)
    current = WifiMetrics("wlan0", bssid=previous.bssid, tx_packets=110, tx_retries=40)
    result = WifiDeltaAnalyzer().calculate(previous, current, 5)
    assert result.tx_retries_per_100_packets == 300
