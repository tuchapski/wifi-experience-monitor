import json
from dataclasses import asdict, replace
from unittest.mock import patch

import pytest

from wem.analysis.wifi_delta import WifiDeltaAnalyzer
from wem.collectors.command import CommandResult
from wem.collectors.wifi import WifiCollector
from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    NetworkMetrics,
    SensorHealthMetrics,
    SensorSnapshot,
    WifiMetrics,
    WifiSurveyMetrics,
)
from wem.storage.database import Database
from wem.storage.repository import SnapshotRepository

SURVEY = """Survey data from wlan0
    frequency: 2412 MHz
    noise: -80 dBm
    channel active time: 1000 ms
    channel busy time: 900 ms
Survey data from wlan0
    frequency: 5260 MHz [in use]
    noise: -95 dBm
    channel active time: 10000 ms
    channel busy time: 3000 ms
    channel receive time: 2000 ms
    channel transmit time: 1000 ms
"""


def wifi() -> WifiMetrics:
    return WifiMetrics(
        "wlan0",
        bssid="aa:bb:cc:dd:ee:ff",
        associated=True,
        frequency_mhz=5260,
        channel_width_mhz=80,
        signal_dbm=-65,
        connected_time_seconds=100,
    )


def collect(output: str = SURVEY, error: str = "", code: int = 0) -> WifiMetrics:
    metrics = wifi()
    collector = WifiCollector("wlan0")
    with patch(
        "wem.collectors.wifi.run_command",
        return_value=CommandResult(output, error, code),
    ) as command:
        collector._collect_survey(metrics)
        command.assert_called_once_with(["iw", "dev", "wlan0", "survey", "dump"])
    assert collector.errors == []
    return metrics


def pair() -> tuple[WifiMetrics, WifiMetrics]:
    previous = collect()
    current = replace(
        previous,
        connected_time_seconds=105,
        survey=replace(
            previous.survey,
            active_ms=12000,
            busy_ms=3500,
            rx_ms=2200,
            tx_ms=1100,
        ),
    )
    return previous, current


def test_uses_in_use_channel_not_first_survey_entry():
    result = collect().survey
    assert result.status == "available"
    assert result.frequency_mhz == 5260
    assert result.noise_dbm == -95
    assert result.snr_db == 30
    assert (result.active_ms, result.busy_ms, result.rx_ms, result.tx_ms) == (
        10000,
        3000,
        2000,
        1000,
    )


@pytest.mark.parametrize(
    "output",
    [
        "",
        "garbage",
        SURVEY.replace(" [in use]", ""),
        SURVEY.replace("5260", "5180"),
        SURVEY + SURVEY,
    ],
)
def test_ambiguous_or_unmatched_surveys_are_unavailable(output):
    survey = collect(output).survey
    assert survey.status == "unavailable"
    assert survey.reason
    assert survey.noise_dbm is None
    assert survey.snr_db is None
    assert survey.active_ms is None


@pytest.mark.parametrize("noise", ["0", "20", "-128", "unknown"])
def test_invalid_noise_is_not_used_for_snr(noise):
    survey = collect(SURVEY.replace("-95", noise)).survey
    assert survey.status == "partial"
    assert survey.noise_dbm is None
    assert survey.snr_db is None
    assert survey.active_ms == 10000


def test_noise_only_driver_does_not_fabricate_counters():
    survey = collect("Survey data from wlan0\nfrequency: 5260 MHz [in use]\nnoise: -96 dBm").survey
    assert survey.status == "partial"
    assert survey.snr_db == 31
    assert survey.active_ms is None
    assert survey.busy_ms is None


def test_no_rssi_means_no_snr():
    metrics = wifi()
    metrics.signal_dbm = None
    with patch("wem.collectors.wifi.run_command", return_value=CommandResult(SURVEY, "", 0)):
        WifiCollector("wlan0")._collect_survey(metrics)
    assert metrics.survey.noise_dbm == -95
    assert metrics.survey.snr_db is None


@pytest.mark.parametrize(
    "error,code,status",
    [
        ("command failed: Operation not supported (-95)", 1, "unsupported"),
        ("command failed: Operation not permitted (-1)", 1, "error"),
        ("command timed out after 5.0 seconds", 124, "error"),
        ("iw not found", 127, "error"),
    ],
)
def test_optional_errors_are_not_connectivity_failures(error, code, status):
    survey = collect("", error, code).survey
    assert survey.status == status
    assert survey.reason == error
    assert survey.noise_dbm is None
    assert survey.active_ms is None


@pytest.mark.parametrize("change", ["disconnected", "unknown_association", "unknown_frequency"])
def test_skips_unverified_connection(change):
    metrics = wifi()
    if change == "disconnected":
        metrics.associated = False
    elif change == "unknown_association":
        metrics.associated = None
    else:
        metrics.frequency_mhz = None
    with patch("wem.collectors.wifi.run_command") as command:
        WifiCollector("wlan0")._collect_survey(metrics)
    command.assert_not_called()
    assert metrics.survey.status == "unavailable"


def test_delta_not_lifetime_ratio():
    previous, current = pair()
    result = WifiDeltaAnalyzer().calculate(previous, current, 5)
    assert result.survey_active_ms_delta == 2000
    assert result.channel_utilization_percent == 25
    assert result.channel_rx_percent == 10
    assert result.channel_tx_percent == 5
    assert result.survey_unavailable_reason is None


@pytest.mark.parametrize(
    "change",
    [
        "interface",
        "bssid",
        "disconnected",
        "reconnect",
        "frequency",
        "width",
        "unknown_width",
        "unmatched_frequency",
        "unsupported",
        "missing_active",
        "unchanged",
        "active_reset",
        "busy_reset",
        "rx_reset",
        "tx_reset",
        "packet_reset",
    ],
)
def test_incomparable_samples_do_not_produce_occupancy(change):
    previous, current = pair()
    if change == "interface":
        current.interface = "wlan1"
    elif change == "bssid":
        current.bssid = "11:22:33:44:55:66"
    elif change == "disconnected":
        current.associated = False
    elif change == "reconnect":
        current.connected_time_seconds = 1
    elif change == "frequency":
        current.frequency_mhz = current.survey.frequency_mhz = 5180
    elif change == "width":
        current.channel_width_mhz = 40
    elif change == "unknown_width":
        previous.channel_width_mhz = current.channel_width_mhz = None
    elif change == "unmatched_frequency":
        current.frequency_mhz = 5180
    elif change == "unsupported":
        previous.survey.status = "unsupported"
    elif change == "missing_active":
        previous.survey.active_ms = None
    elif change == "unchanged":
        current.survey.active_ms = previous.survey.active_ms
    elif change == "packet_reset":
        previous.tx_packets, current.tx_packets = 100, 1
    else:
        setattr(current.survey, change.replace("_reset", "_ms"), 0)
    result = WifiDeltaAnalyzer().calculate(previous, current, 5)
    assert result.channel_utilization_percent is None
    assert result.channel_rx_percent is None
    assert result.channel_tx_percent is None
    assert result.survey_unavailable_reason or result.unavailable_reason


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf")])
def test_invalid_intervals_do_not_produce_occupancy(interval):
    previous, current = pair()
    result = WifiDeltaAnalyzer().calculate(previous, current, interval)
    assert result.channel_utilization_percent is None


def test_zero_busy_is_a_real_zero_not_missing():
    previous, current = pair()
    current.survey.busy_ms = previous.survey.busy_ms
    result = WifiDeltaAnalyzer().calculate(previous, current, 5)
    assert result.channel_utilization_percent == 0


@pytest.mark.parametrize("field,value", [("busy_ms", None), ("busy_ms", 6000), ("rx_ms", None)])
def test_partial_or_inconsistent_deltas_preserve_independent_metrics(field, value):
    previous, current = pair()
    setattr(current.survey, field, value)
    result = WifiDeltaAnalyzer().calculate(previous, current, 5)
    assert result.channel_tx_percent == 5
    assert result.survey_unavailable_reason
    if field == "busy_ms":
        assert result.channel_utilization_percent is None
        assert result.channel_rx_percent == 10
    else:
        assert result.channel_rx_percent is None
        assert result.channel_utilization_percent == 25


def test_optional_failure_does_not_disable_station_deltas():
    previous, current = pair()
    current.survey = WifiSurveyMetrics(status="unsupported")
    previous.tx_packets, current.tx_packets = 100, 200
    previous.tx_retries, current.tx_retries = 20, 30
    result = WifiDeltaAnalyzer().calculate(previous, current, 5)
    assert result.tx_retries_per_100_packets == 10
    assert result.channel_utilization_percent is None


def test_survey_persists_in_snapshot_json(tmp_path):
    previous, current = pair()
    delta = WifiDeltaAnalyzer().calculate(previous, current, 5)
    snapshot = SensorSnapshot.create(
        health=SensorHealthMetrics("wlan0"),
        calibration=CalibrationResult(status="ok", calibrated=True),
        wifi=current,
        wifi_delta=delta,
        network=NetworkMetrics("wlan0"),
        connectivity=ConnectivityMetrics(),
    )
    database = Database(str(tmp_path / "survey.db"))
    database.initialize()
    record = SnapshotRepository(database).save(snapshot)
    saved = json.loads(record.snapshot_json)
    assert saved["wifi"]["survey"] == asdict(current.survey)
    assert saved["wifi_delta"]["channel_utilization_percent"] == 25
    assert saved["wifi_delta"]["survey_unavailable_reason"] is None
