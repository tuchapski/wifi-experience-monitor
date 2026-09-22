from datetime import UTC, datetime, timedelta

from wem.analysis.connection_cycle import ConnectionCycleTracker
from wem.collectors.networkmanager_events import (
    NetworkManagerDeviceEvent,
    NetworkManagerEventMonitor,
)
from wem.models.metrics import ConnectivityMetrics, NetworkMetrics, WifiMetrics

T0 = datetime(2026, 9, 22, 15, tzinfo=UTC)


def test_gdbus_device_path_and_state_changed_parsing() -> None:
    path = NetworkManagerEventMonitor.parse_device_path(
        "(objectpath '/org/freedesktop/NetworkManager/Devices/7',)"
    )
    assert path == "/org/freedesktop/NetworkManager/Devices/7"

    line = (
        "/org/freedesktop/NetworkManager/Devices/7: "
        "org.freedesktop.NetworkManager.Device.StateChanged "
        "(uint32 70, uint32 50, uint32 0)"
    )
    event = NetworkManagerEventMonitor.parse_state_changed(line, observed_at=T0)
    assert event is not None
    assert event.observed_at == T0
    assert event.new_state == 70
    assert event.old_state == 50
    assert event.reason == 0
    assert event.new_state_name == "ip_config"


def test_non_state_signal_is_ignored() -> None:
    line = (
        "/org/freedesktop/NetworkManager/Devices/7: "
        "org.freedesktop.DBus.Properties.PropertiesChanged ({},)"
    )
    assert NetworkManagerEventMonitor.parse_state_changed(line, observed_at=T0) is None


def test_networkmanager_events_refine_connection_phase_timing() -> None:
    tracker = ConnectionCycleTracker()
    events = [
        NetworkManagerDeviceEvent(T0, new_state=40, old_state=30, reason=0),
        NetworkManagerDeviceEvent(
            T0 + timedelta(milliseconds=250),
            new_state=50,
            old_state=40,
            reason=0,
        ),
        NetworkManagerDeviceEvent(
            T0 + timedelta(milliseconds=1200),
            new_state=70,
            old_state=50,
            reason=0,
        ),
        NetworkManagerDeviceEvent(
            T0 + timedelta(milliseconds=2100),
            new_state=80,
            old_state=70,
            reason=0,
        ),
        NetworkManagerDeviceEvent(
            T0 + timedelta(milliseconds=2500),
            new_state=100,
            old_state=80,
            reason=0,
        ),
    ]

    cycle = tracker.observe(
        WifiMetrics(
            "wlan0",
            ssid="CORP",
            bssid="aa:bb:cc:dd:ee:01",
            associated=True,
            authenticated=True,
            authorized=True,
            connected_time_seconds=2,
        ),
        NetworkMetrics("wlan0", ipv4_address="192.0.2.10"),
        ConnectivityMetrics(gateway_reachable=True, dns_success=True),
        observed_at=T0 + timedelta(seconds=5),
        networkmanager_events=events,
        event_monitor_status="active",
    )

    assert cycle is not None
    assert cycle.session_type == "initial_connect"
    assert cycle.started_at == T0.isoformat()
    assert cycle.timing_source == "networkmanager_dbus+sampling"
    assert cycle.event_monitor_status == "active"
    assert cycle.networkmanager_state == 100
    assert cycle.networkmanager_state_name == "activated"
    assert cycle.networkmanager_event_count == 5

    association = cycle.stages["association"]
    assert association.elapsed_ms == 1200.0
    assert association.estimated is False
    assert association.source == "networkmanager_dbus"

    ipv4 = cycle.stages["dhcp"]
    assert ipv4.elapsed_ms == 2100.0
    assert ipv4.estimated is False
    assert ipv4.source == "networkmanager_dbus"

    authentication = cycle.stages["authentication"]
    assert authentication.elapsed_ms == 5000.0
    assert authentication.estimated is True
    assert authentication.source == "sampling"

    assert cycle.total_time_ms == 5000.0
    assert cycle.stages["network_ready"].estimated is True


def test_event_monitor_failure_keeps_sampling_fallback() -> None:
    tracker = ConnectionCycleTracker()
    cycle = tracker.observe(
        WifiMetrics(
            "wlan0",
            ssid="CORP",
            bssid="aa:bb:cc:dd:ee:01",
            associated=True,
            authenticated=True,
            authorized=True,
            connected_time_seconds=10,
        ),
        NetworkMetrics("wlan0", ipv4_address="192.0.2.10"),
        ConnectivityMetrics(gateway_reachable=True, dns_success=True),
        observed_at=T0,
        event_monitor_status="unavailable",
        event_monitor_reason="gdbus is not installed",
    )

    assert cycle is not None
    assert cycle.session_type == "observed_existing"
    assert cycle.timing_source == "sampling"
    assert cycle.event_monitor_status == "unavailable"
    assert cycle.event_monitor_reason == "gdbus is not installed"
    assert cycle.stages["association"].source == "sampling"
