from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path

import pytest
from wifi_agent.collectors.connectivity import ProbeResult
from wifi_agent.config import AgentSettings
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.runtime.experience_profile import ExperienceProfileRuntime, RuntimeExperienceProfile
from wifi_agent.storage import AgentIdentity

VERSION = "exp_" + "a" * 32


def payload(enabled=True):
    return {
        "version": VERSION,
        "profile": {
            "enabled": enabled,
            "dns_query": "office.example",
            "internet_target": "192.0.2.1",
            "https_url": "https://app.example",
            "interval_seconds": 10,
            "timeout_seconds": 4,
        },
    }


def manager(tmp_path):
    settings = AgentSettings(
        "http://localhost", None, tmp_path, "test", "sensor", 5, 5, 1, 10, 5, 24, 10, "wlan0"
    )
    identity = AgentIdentity("agt_test", "token", settings.server_url, datetime.now(UTC))
    return ExperienceProfileRuntime(settings, identity)


def test_profile_pending_then_applied_persisted_and_reloaded(tmp_path: Path):
    runtime = manager(tmp_path)
    runtime.receive(payload())
    assert runtime.version is None
    assert runtime.apply()
    assert runtime.version == VERSION
    assert runtime.interval_seconds == 10
    restored = manager(tmp_path)
    assert restored.version == VERSION
    assert restored.timeout_seconds == 4
    restored.receive(None)  # Server unavailable/older Server does not reset the saved policy.
    assert restored.version == VERSION
    restored.receive(payload())
    assert not restored.apply()


def test_disabled_profile_restores_environment_targets_and_cadence(tmp_path):
    runtime = manager(tmp_path)
    runtime.receive(payload(False))
    runtime.apply()
    probes = runtime.make_probes("wlan0")
    try:
        assert probes.dns_query == runtime.settings.dns_probe_query
        assert runtime.interval_seconds == runtime.settings.synthetic_probe_interval_seconds
        assert probes.profile_version == VERSION
    finally:
        probes.close()


def test_probe_metadata_retains_start_context_clock_and_effective_profile(tmp_path):
    runtime = manager(tmp_path)
    runtime.receive(payload())
    runtime.apply()
    probes = runtime.make_probes("wlan0")
    time = datetime.now(UTC)
    future = Future()
    future.set_result(
        ProbeResult(
            [
                Observation(
                    "synthetic",
                    ObservationKind.STATE,
                    "network.dns_success",
                    True,
                    observed_at=time,
                    labels={"interface": "wlan0", "target": "office.example"},
                )
            ],
            [],
        )
    )
    probes._pending["dns"] = future
    probes._contexts["dns"] = {"ssid": "Office", "band": "5ghz", "bssid": "old-bssid"}
    result = probes.poll()
    try:
        outcome = result.observations[0]
        assert outcome.observed_at == time
        assert outcome.metadata["profile_version"] == VERSION
        assert outcome.labels["ssid"] == "Office"
        assert outcome.labels["configured_interval_seconds"] == "10.0"
        assert "interval_seconds" not in outcome.labels
        assert result.observations[-1].metadata["profile_version"] == VERSION
    finally:
        probes.close()


@pytest.mark.parametrize(
    "updates",
    [
        {"internet_target": "--help"},
        {"interval_seconds": True},
        {"timeout_seconds": float("nan")},
        {"https_url": "http://example.com"},
    ],
)
def test_invalid_runtime_profile_keeps_applied_configuration(tmp_path, updates):
    runtime = manager(tmp_path)
    runtime.receive(payload())
    runtime.apply()
    invalid = payload()
    invalid["version"] = "exp_" + "b" * 32
    invalid["profile"].update(updates)
    with pytest.raises(ValueError):
        runtime.receive(invalid)
    assert runtime.version == VERSION
    assert runtime.pending is None


def test_profile_copy_bound_to_agent_identity(tmp_path):
    runtime = manager(tmp_path)
    runtime.receive(payload())
    runtime.apply()
    identity = AgentIdentity("agt_other", "token", "http://localhost", datetime.now(UTC))
    restored = ExperienceProfileRuntime(runtime.settings, identity)
    assert restored.version is None
    with pytest.raises(ValueError):
        RuntimeExperienceProfile.parse({"version": "old", "profile": {}})
