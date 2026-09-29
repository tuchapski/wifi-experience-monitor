from pathlib import Path
from unittest.mock import patch

import pytest
from wifi_agent.collectors.command import CommandResult
from wifi_agent.collectors.rf_scan import (
    RfScanCollector,
    frequency_to_band,
    frequency_to_channel,
    parse_iw_scan,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parses_ax201_scan_excerpt_without_requiring_optional_information_elements() -> None:
    bsses = parse_iw_scan(fixture("iw_scan_ax201_excerpt.txt"), "wlp0s20f3")

    assert len(bsses) == 7
    associated = next(bss for bss in bsses if bss.associated)
    assert associated.bssid == "98:7e:ca:8a:3e:0e"
    assert associated.ssid == "AeP"
    assert associated.frequency_mhz == 5805
    assert associated.channel == 161
    assert associated.band == "5ghz"
    assert associated.rssi_dbm == -61.0

    same_ssid = [bss for bss in bsses if bss.ssid == "AeP"]
    assert len(same_ssid) == 3
    assert next(bss for bss in same_ssid if bss.frequency_mhz == 2437).channel == 6


def test_parses_phy_security_width_and_ap_advertised_bss_load() -> None:
    bsses = parse_iw_scan(fixture("iw_scan_capabilities.txt"), "wlan0")

    assert len(bsses) == 2
    corp = bsses[0]
    assert corp.channel == 36
    assert corp.channel_width_mhz == 80
    assert corp.beacon_interval_tu == 100
    assert corp.privacy is True
    assert corp.security == ("RSN",)
    assert corp.phy_capabilities == ("HT", "VHT", "HE")
    assert corp.bss_load_station_count == 12
    assert corp.bss_load_channel_utilization_raw == 64
    assert corp.bss_load_channel_utilization_percent == pytest.approx(25.098, rel=1e-3)
    assert corp.last_seen_ms == 42

    hidden = bsses[1]
    assert hidden.ssid is None
    assert hidden.band == "6ghz"
    assert hidden.channel == 5
    assert hidden.channel_width_mhz == 160
    assert hidden.phy_capabilities == ("HE", "EHT")


@pytest.mark.parametrize(
    ("frequency", "band", "channel"),
    [
        (2412, "2.4ghz", 1),
        (2484, "2.4ghz", 14),
        (5805, "5ghz", 161),
        (5935, "6ghz", 2),
        (5955, "6ghz", 1),
        (5975, "6ghz", 5),
        (9000, "unknown", None),
    ],
)
def test_frequency_normalization(frequency: int, band: str, channel: int | None) -> None:
    assert frequency_to_band(frequency) == band
    assert frequency_to_channel(frequency) == channel


@patch("wifi_agent.collectors.rf_scan.run_command")
def test_rf_scan_collector_runs_scan_with_independent_timeout(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        fixture("iw_scan_ax201_excerpt.txt"),
        "",
        0,
    )

    result = RfScanCollector("wlp0s20f3", timeout_seconds=18.0).collect()

    assert result.success is True
    assert len(result.bsses) == 7
    assert result.associated_bss is not None
    assert result.duration_ms >= 0
    mock_run_command.assert_called_once_with(
        ["iw", "dev", "wlp0s20f3", "scan"],
        timeout=18.0,
    )


@patch("wifi_agent.collectors.rf_scan.run_command")
def test_rf_scan_collector_preserves_scan_failure_as_runtime_evidence(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult("", "Operation not permitted", 1)

    result = RfScanCollector("wlp0s20f3").collect()

    assert result.success is False
    assert result.bsses == ()
    assert result.error == "iw scan failed: Operation not permitted"
