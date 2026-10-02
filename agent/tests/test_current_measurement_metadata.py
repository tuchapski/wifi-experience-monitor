from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from wifi_agent.cli import _update_probe_cache
from wifi_agent.collectors.command import CommandResult
from wifi_agent.collectors.connectivity import ProbeResult, probe_ping
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.processors import StateProcessor
from wifi_agent.runtime.synthetic import SyntheticProbeRuntime

NOW = datetime(2026, 10, 2, 17, tzinfo=UTC)


def test_cached_probe_keeps_its_own_clock_source_target_and_interval():
    probe_time = NOW - timedelta(seconds=12)
    snapshot = StateProcessor().build(
        [
            Observation("wifi", ObservationKind.STATE, "wifi.connected", True, observed_at=NOW),
            Observation(
                "synthetic",
                ObservationKind.GAUGE,
                "network.gateway_latency_ms",
                5,
                unit="ms",
                observed_at=probe_time,
                labels={"target": "192.0.2.1", "interface": "wlan0", "interval_seconds": "4"},
            ),
        ]
    )
    payload = snapshot.to_payload()
    assert snapshot.observed_at == NOW
    metadata = payload["measurement_metadata"]["network.gateway_latency_ms"]
    assert metadata["observed_at"] == probe_time.isoformat()
    assert metadata["source"] == "synthetic"
    assert metadata["labels"]["target"] == "192.0.2.1"
    assert metadata["interval_seconds"] == 4
    assert metadata["sample_count"] == 1


def test_tool_error_replaces_previous_success_in_cache_and_recovers_on_next_result():
    runtime = SyntheticProbeRuntime(
        "wlan0",
        dns_query="example.com",
        internet_target="192.0.2.2",
        https_url="https://example.com",
        timeout_seconds=5,
    )
    successful = Observation(
        "synthetic",
        ObservationKind.STATE,
        "network.internet_reachable",
        True,
        observed_at=NOW,
        labels={"target": "192.0.2.2"},
    )
    cache = {successful.metric: successful}
    future = Future()
    future.set_result(ProbeResult([], ["internet ping collection failed: permission denied"]))
    runtime._pending["internet"] = future
    result = runtime.poll()
    _update_probe_cache(cache, result.observations)
    assert "network.internet_reachable" not in cache
    assert cache["network.internet_collection_error"].value.endswith("permission denied")
    future = Future()
    future.set_result(ProbeResult([successful], []))
    runtime._pending["internet"] = future
    recovered = runtime.poll()
    _update_probe_cache(cache, recovered.observations)
    assert cache["network.internet_reachable"].value is True
    assert cache["network.internet_collection_error"].value is None
    assert cache["network.internet_collection_error"].observed_at == NOW
    runtime.close()


def test_worker_exception_becomes_domain_error_not_false_network_failure():
    runtime = SyntheticProbeRuntime(
        "wlan0",
        dns_query="example.com",
        internet_target="192.0.2.2",
        https_url="https://example.com",
        timeout_seconds=5,
    )
    future = Future()
    future.set_exception(OSError("missing executable"))
    runtime._pending["dns"] = future
    result = runtime.poll()
    assert result.errors
    values = {item.metric: item.value for item in result.observations}
    assert "network.dns_success" not in values
    assert "missing executable" in values["network.dns_collection_error"]
    runtime.close()


@patch("wifi_agent.collectors.connectivity.run_command")
def test_ping_denominators_and_extremes_survive_snapshot(mock_run):
    mock_run.return_value = CommandResult(
        "4 packets transmitted, 3 received, 25% packet loss\n"
        "rtt min/avg/max/mdev = 1.000/8.000/20.000/5.000 ms",
        "",
        0,
    )
    result = probe_ping("gateway", "192.0.2.1", "wlan0", 5)
    payload = StateProcessor().build(result.observations).to_payload()
    assert payload["network"]["gateway_packets_sent"] == 4
    assert payload["network"]["gateway_packets_received"] == 3
    assert payload["network"]["gateway_latency_max_ms"] == 20
    assert payload["network"]["gateway_packet_loss_percent"] == 25
