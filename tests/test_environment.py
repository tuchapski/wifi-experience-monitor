import json
from datetime import UTC, datetime, timedelta

from wem.analysis.environment import EnvironmentChangeAnalyzer
from wem.models.metrics import WifiMetrics
from wem.storage.database import Database
from wem.storage.history import HistoryRepository
from wem.storage.models import SnapshotRecord


def test_first_sample_has_no_environment_change():
    analyzer = EnvironmentChangeAnalyzer()
    sample = WifiMetrics("wlan0", ssid="Office", bssid="aa:bb:cc:dd:ee:ff")

    assert analyzer.compare(sample, sample) == []


def test_radio_and_association_changes_are_explicit():
    analyzer = EnvironmentChangeAnalyzer()
    previous = WifiMetrics(
        "wlan0",
        ssid="Office",
        bssid="aa:bb:cc:dd:ee:ff",
        channel=36,
        frequency_mhz=5180,
        channel_width_mhz=80,
        tx_phy_mode="VHT",
        rx_phy_mode="VHT",
        associated=True,
    )
    current = WifiMetrics(
        "wlan0",
        ssid="Guest",
        bssid="11:22:33:44:55:66",
        channel=149,
        frequency_mhz=5745,
        channel_width_mhz=40,
        tx_phy_mode="HE",
        rx_phy_mode="HE",
        associated=True,
    )

    changes = analyzer.compare(previous, current)
    assert {change.code for change in changes} == {
        "WIFI_SSID_CHANGED",
        "WIFI_BSSID_CHANGED",
        "WIFI_CHANNEL_CHANGED",
        "WIFI_FREQUENCY_MHZ_CHANGED",
        "WIFI_CHANNEL_WIDTH_MHZ_CHANGED",
        "WIFI_TX_PHY_CHANGED",
        "WIFI_RX_PHY_CHANGED",
    }
    assert all(change.severity == "info" for change in changes)


def test_unknown_values_do_not_create_false_change():
    previous = WifiMetrics("wlan0", ssid="Office", channel=36)
    current = WifiMetrics("wlan0", ssid=None, channel=40)

    changes = EnvironmentChangeAnalyzer().compare(previous, current)
    assert [change.code for change in changes] == ["WIFI_CHANNEL_CHANGED"]


def test_history_returns_events_with_their_sample_timestamp(tmp_path):
    database = Database(str(tmp_path / "events.db"))
    database.initialize()
    timestamp = datetime(2026, 9, 21, 12, tzinfo=UTC)
    snapshot = {
        "environment_changes": [
            {
                "code": "WIFI_CHANNEL_CHANGED",
                "field": "channel",
                "previous": 36,
                "current": 149,
                "message": "Wi-Fi channel changed: 36 → 149.",
                "severity": "info",
            }
        ]
    }
    with database.session() as session:
        session.add(
            SnapshotRecord(
                timestamp=timestamp.replace(tzinfo=None),
                interface="wlan0",
                snapshot_json=json.dumps(snapshot),
            )
        )
        session.commit()

    result = HistoryRepository(database).window(
        "wlan0", timestamp, timestamp + timedelta(minutes=1)
    )
    assert len(result["events"]) == 1
    assert result["events"][0]["field"] == "channel"
    assert result["events"][0]["timestamp"].endswith("+00:00")
