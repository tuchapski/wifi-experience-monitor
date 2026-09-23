from datetime import UTC, datetime, timedelta

from wem.analysis.connection_cycle import ConnectionCycleTracker
from wem.models.metrics import ConnectivityMetrics, NetworkMetrics, WifiMetrics

T0 = datetime(2026, 9, 22, 12, tzinfo=UTC)


def sample(
    *,
    associated: bool | None,
    ssid: str | None = "CORP",
    bssid: str | None = "aa:bb:cc:dd:ee:01",
    authenticated: bool | None = True,
    authorized: bool | None = True,
    connected_time: int | None = 10,
    ipv4: str | None = "192.0.2.10",
    gateway: bool | None = True,
    dns: bool | None = True,
):
    return (
        WifiMetrics(
            "wlan0",
            ssid=ssid,
            bssid=bssid,
            associated=associated,
            authenticated=authenticated,
            authorized=authorized,
            connected_time_seconds=connected_time,
        ),
        NetworkMetrics("wlan0", ipv4_address=ipv4),
        ConnectivityMetrics(gateway_reachable=gateway, dns_success=dns),
    )


def test_existing_connection_never_invents_stage_duration():
    tracker = ConnectionCycleTracker()
    cycle = tracker.observe(*sample(associated=True), observed_at=T0)
    assert cycle is not None
    assert cycle.session_type == "observed_existing"
    assert cycle.state == "ready"
    assert cycle.started_at is None
    assert cycle.total_time_ms is None
    assert cycle.stages["authentication"].status == "observed"
    assert cycle.stages["authentication"].elapsed_ms is None
    assert cycle.stages["authorization"].elapsed_ms is None


def test_reconnect_records_estimated_upper_bound():
    tracker = ConnectionCycleTracker()
    assert (
        tracker.observe(
            *sample(
                associated=False,
                bssid=None,
                authenticated=False,
                authorized=False,
                connected_time=None,
                ipv4=None,
                gateway=None,
                dns=None,
            ),
            observed_at=T0,
        )
        is None
    )
    cycle = tracker.observe(
        *sample(associated=True, connected_time=1),
        observed_at=T0 + timedelta(seconds=5),
    )
    assert cycle is not None
    assert cycle.session_type == "initial_connect"
    assert cycle.started_at == T0.isoformat()
    assert cycle.sample_resolution_ms == 5000.0
    assert cycle.total_time_ms == 5000.0
    assert cycle.stages["network_ready"].estimated is True


def test_disconnect_then_reconnect_creates_new_session():
    tracker = ConnectionCycleTracker()
    first = tracker.observe(*sample(associated=True), observed_at=T0)
    assert first is not None
    first_id = first.session_id
    closed = tracker.observe(
        *sample(
            associated=False,
            bssid=None,
            authenticated=False,
            authorized=False,
            connected_time=None,
            ipv4=None,
            gateway=None,
            dns=None,
        ),
        observed_at=T0 + timedelta(seconds=5),
    )
    assert closed is not None and closed.state == "disconnected"
    assert closed.completed_at == (T0 + timedelta(seconds=5)).isoformat()
    second = tracker.observe(
        *sample(associated=True, connected_time=1),
        observed_at=T0 + timedelta(seconds=10),
    )
    assert second is not None
    assert second.session_id != first_id
    assert second.session_type == "reconnect"


def test_bssid_change_is_roam_and_does_not_claim_exact_timing():
    tracker = ConnectionCycleTracker()
    tracker.observe(*sample(associated=True), observed_at=T0)
    cycle = tracker.observe(
        *sample(associated=True, bssid="aa:bb:cc:dd:ee:02", connected_time=11),
        observed_at=T0 + timedelta(seconds=5),
    )
    assert cycle is not None
    assert cycle.session_type == "roam"
    assert cycle.sample_resolution_ms == 5000.0
    assert any("continuously available" in item for item in cycle.limitations)


def test_ssid_change_is_network_change():
    tracker = ConnectionCycleTracker()
    tracker.observe(*sample(associated=True), observed_at=T0)
    cycle = tracker.observe(
        *sample(associated=True, ssid="GUEST", connected_time=1),
        observed_at=T0 + timedelta(seconds=5),
    )
    assert cycle is not None
    assert cycle.session_type == "network_change"


def test_connected_time_reset_detects_reassociation():
    tracker = ConnectionCycleTracker()
    tracker.observe(*sample(associated=True, connected_time=120), observed_at=T0)
    cycle = tracker.observe(
        *sample(associated=True, connected_time=2),
        observed_at=T0 + timedelta(seconds=5),
    )
    assert cycle is not None
    assert cycle.session_type == "reassociation"


def test_authentication_and_authorization_can_remain_unavailable():
    tracker = ConnectionCycleTracker()
    cycle = tracker.observe(
        *sample(associated=True, authenticated=None, authorized=None),
        observed_at=T0,
    )
    assert cycle is not None
    assert cycle.stages["authentication"].status == "unavailable"
    assert cycle.stages["authorization"].status == "unavailable"
    assert cycle.state == "ready"
