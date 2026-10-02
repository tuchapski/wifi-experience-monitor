import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session
from wifi_server.analysis.client_detector import consume_snapshot
from wifi_server.db.experience_models import AgentExperienceMonitor
from wifi_server.db.models import Agent
from wifi_server.monitor_schemas import ExperienceProfile, ExperienceProfileUpdate
from wifi_server.schemas import AgentCurrentStateResponse
from wifi_server.services.client_experience import evaluate_client_experience
from wifi_server.services.client_monitor import evaluate_detection, get_profile, update_profile

NOW = datetime(2026, 10, 2, 18, tzinfo=UTC)
VERSION = "exp_" + "a" * 32


def snapshot(seconds=0, **changes):
    time = NOW + timedelta(seconds=seconds)
    wifi = {"connected": True, "interface": "wlan0", "ssid": "Office", "frequency_mhz": 5180}
    network = {
        "gateway": "192.0.2.1",
        "gateway_reachable": True,
        "gateway_latency_ms": 5,
        "gateway_packet_loss_percent": 0,
        "dns_success": True,
        "dns_latency_ms": 10,
        "internet_reachable": True,
        "internet_latency_ms": 15,
        "internet_packet_loss_percent": 0,
        "https_success": True,
        "https_total_ms": 50,
    }
    wifi.update(changes.pop("wifi", {}))
    network.update(changes)
    metadata = {}
    for prefix, values in (("wifi", wifi), ("network", network)):
        for key in values:
            target = (
                "192.0.2.1"
                if key.startswith("gateway_")
                else "1.1.1.1"
                if key.startswith("internet_")
                else "https://example.com"
                if key.startswith("https_")
                else "example.com"
            )
            metadata[f"{prefix}.{key}"] = {
                "observed_at": time,
                "source": "test",
                "profile_version": VERSION,
                "labels": {
                    "interface": "wlan0",
                    "target": target,
                    "ssid": wifi.get("ssid") or "",
                    "band": "5ghz",
                },
            }
    return AgentCurrentStateResponse(
        agent_id="agt_test",
        observed_at=time,
        updated_at=time,
        wifi=wifi,
        network=network,
        measurement_metadata=metadata,
    )


def step(previous=None, seconds=0, *, profile=None, state=None, **changes):
    state = state or snapshot(seconds, **changes)
    profile = profile or ExperienceProfile(enabled=True)
    experience = evaluate_client_experience("agt_test", state, online=True, now=state.observed_at)
    return consume_snapshot(previous or {}, state, experience, profile, VERSION)


def rule(state, metric="network.gateway_latency_ms"):
    return state["rules"][metric]


def test_transient_spike_does_not_confirm_and_repeated_snapshots_do_not_count():
    initial = step(gateway_latency_ms=100)
    assert rule(initial)["status"] == "candidate"
    repeated = deepcopy(snapshot(gateway_latency_ms=100))
    repeated.observed_at += timedelta(seconds=20)
    after = step(initial, state=repeated)
    assert rule(after)["consecutive_samples"] == 1
    assert rule(after)["status"] == "candidate"
    recovered = step(after, 25)
    assert rule(recovered)["status"] == "normal"


def test_objective_confirmation_latency_and_hysteresis_recovery():
    state = {}
    for second in (0, 5, 10, 15):
        state = step(state, second, gateway_latency_ms=100)
    assert rule(state)["status"] == "active"
    assert rule(state)["observed_duration_seconds"] == 15
    assert rule(state)["kind"] == "objective"
    state = step(state, 20, gateway_latency_ms=45)  # Under objective, above recovery boundary.
    assert rule(state)["status"] == "active"
    for second in (25, 30):
        state = step(state, second, gateway_latency_ms=30)
        assert rule(state)["status"] == "recovering"
    state = step(state, 35, gateway_latency_ms=30)
    assert rule(state)["status"] == "recovered"
    state = step(state, 40, gateway_latency_ms=100)
    assert rule(state)["since"] == (NOW + timedelta(seconds=40)).isoformat()
    assert rule(state)["observed_duration_seconds"] == 0


def test_explicit_short_failure_is_immediate_and_cannot_be_hidden_by_other_domains():
    state = step(https_success=False, https_total_ms=None)
    assert rule(state, "network.https_success")["status"] == "active"
    assert rule(state, "network.gateway_reachable")["status"] == "normal"
    assert rule(state, "network.https_total_ms")["status"] == "unknown"


def test_loss_objective_and_zero_boundary():
    profile = ExperienceProfile(enabled=True, local_network={"packet_loss_percent": 0})
    state = {}
    for second in (0, 5, 10, 15):
        state = step(state, second, profile=profile, gateway_packet_loss_percent=25)
    assert rule(state, "network.gateway_packet_loss_percent")["status"] == "active"
    for second in (20, 25, 30):
        state = step(state, second, profile=profile, gateway_packet_loss_percent=0)
    assert rule(state, "network.gateway_packet_loss_percent")["status"] == "recovered"


def test_error_and_missing_evidence_do_not_confirm_recovery_and_gap_resets_streak():
    state = step(https_success=False)
    failed = snapshot(5, https_collection_error="curl missing")
    state = step(state, state=failed)
    assert rule(state, "network.https_success")["status"] == "unknown"
    assert rule(state, "network.https_success")["confirmed"] is True
    state = step(state, 60)
    assert rule(state, "network.https_success")["status"] == "recovering"
    assert rule(state, "network.https_success")["evidence_gap"] is True
    state = step(state, 100)  # Gap during recovery starts a fresh recovery window.
    assert rule(state, "network.https_success")["status"] == "recovering"
    state = step(state, 105)
    state = step(state, 110)
    assert rule(state, "network.https_success")["status"] == "recovered"
    pending = step(gateway_latency_ms=100)
    pending = step(pending, 40, gateway_latency_ms=100)
    assert rule(pending)["consecutive_samples"] == 1


def test_reference_requires_distinct_comparable_samples_and_freezes_before_relative_alert():
    state = {}
    for second in range(0, 150, 5):
        state = step(state, second)
    baseline = deepcopy(rule(state)["baseline"])
    assert baseline["status"] == "ready"
    assert baseline["samples"] == 30
    assert baseline["median"] == baseline["p95"] == 5
    for second in (150, 155, 160, 165):
        state = step(state, second, gateway_latency_ms=30)  # Under objective 50, above relative 15.
    assert rule(state)["status"] == "active"
    assert rule(state)["kind"] == "relative"
    assert rule(state)["baseline"] == baseline
    for second in range(170, 400, 5):
        state = step(state, second, gateway_latency_ms=100)
    assert rule(state)["baseline"] == baseline
    assert json.loads(json.dumps(state)) == state  # Persistable and restart-independent.


def test_reference_does_not_learn_objective_failures_and_ignores_rssi_as_service_failure():
    state = {}
    for second in range(0, 150, 5):
        state = step(state, second, gateway_latency_ms=100, wifi={"rssi_dbm": -90})
    assert rule(state)["baseline"]["samples"] == 0
    assert "wifi.rssi_dbm" not in state["rules"]
    assert rule(state, "wifi.connected")["status"] == "normal"


@pytest.mark.parametrize(
    "kind", ["legacy", "old_profile", "changed_target", "probe_before_roam", "nan", "future"]
)
def test_incompatible_or_invalid_evidence_is_unknown(kind):
    state = snapshot()
    meta = state.measurement_metadata["network.gateway_latency_ms"]
    if kind == "legacy":
        state.measurement_metadata = {}
    elif kind == "old_profile":
        meta.profile_version = "old"
    elif kind == "changed_target":
        meta.labels["target"] = "192.0.2.99"
    elif kind == "probe_before_roam":
        meta.labels["ssid"] = "Old office"
    elif kind == "nan":
        state.network.gateway_latency_ms = float("nan")
    else:
        meta.observed_at += timedelta(seconds=6)
    assert rule(step(state=state))["status"] == "unknown"


def test_context_switch_forms_new_reference_and_returning_context_reuses_frozen_reference():
    state = {}
    for second in range(0, 150, 5):
        state = step(state, second)
    reference = rule(state)["baseline"]
    state = step(state, 150, wifi={"ssid": "Other"})
    assert rule(state)["baseline"]["status"] == "forming"
    state = step(state, 155)
    assert rule(state)["baseline"] == reference
    for index in range(50):
        state = step(state, 160 + index * 5, wifi={"ssid": f"Office-{index}"})
    assert len(state["references"]) <= 32


def test_disconnection_observed_with_no_ssid_is_active_not_unknown():
    state = step(wifi={"connected": False, "ssid": None, "frequency_mhz": None})
    assert rule(state, "wifi.connected")["status"] == "active"
    assert rule(state)["status"] == "unknown"


def test_profile_edit_is_versioned_and_conflict_checked_without_rebuilding_on_identical_save():
    session = Mock(spec=Session)
    agent = Agent(id="agt_test")
    monitor = AgentExperienceMonitor(
        agent_id="agt_test",
        profile_version=VERSION,
        profile=ExperienceProfile(enabled=True).model_dump(),
        detector_state={"keep": True},
    )
    session.get.side_effect = lambda model, _id, **kw: (
        agent if model is Agent else monitor if model is AgentExperienceMonitor else None
    )
    unchanged = update_profile(
        session,
        "agt_test",
        ExperienceProfileUpdate(expected_version=VERSION, profile=ExperienceProfile(enabled=True)),
    )
    assert unchanged.version == VERSION
    assert monitor.detector_state == {"keep": True}
    changed = update_profile(
        session,
        "agt_test",
        ExperienceProfileUpdate(
            expected_version=VERSION,
            profile=ExperienceProfile(enabled=True, location="Meeting room"),
        ),
    )
    assert changed.version != VERSION
    assert monitor.detector_state == {}
    with pytest.raises(Exception) as failure:
        update_profile(
            session,
            "agt_test",
            ExperienceProfileUpdate(expected_version=VERSION, profile=ExperienceProfile()),
        )
    assert failure.value.status_code == 409


def test_current_view_is_read_only_and_offline_is_not_recovery():
    raw = step(https_success=False)
    monitor = AgentExperienceMonitor(
        profile_version=VERSION,
        profile=ExperienceProfile(enabled=True).model_dump(),
        detector_state=raw,
    )
    state = snapshot(https_success=False)
    before = deepcopy(raw)
    current = evaluate_detection("agt_test", monitor, state, online=True, now=NOW)
    assert current.status == "active"
    assert current.active_count == 1
    offline = evaluate_detection(
        "agt_test", monitor, state, online=False, now=NOW + timedelta(seconds=60)
    )
    assert offline.status == "unknown"
    assert all(item.status == "unknown" for item in offline.findings)
    assert raw == before
    assert evaluate_detection("agt_test", None, None, online=True, now=NOW).status == "disabled"


@pytest.mark.parametrize(
    "updates",
    [
        {"interval_seconds": 1},
        {"timeout_seconds": 60},
        {"dns_query": "--help"},
        {"https_url": "https://user:password@example.com"},
        {"internet_target": "x y"},
        {"dns": {"latency_ms": float("nan")}},
    ],
)
def test_invalid_profiles_rejected(updates):
    with pytest.raises(ValidationError):
        ExperienceProfile(**updates)


def test_unconfigured_client_and_unknown_agent_profiles():
    session = Mock(spec=Session)
    session.get.side_effect = lambda model, _id, **kw: (
        Agent(id="agt_test") if model is Agent else None
    )
    assert get_profile(session, "agt_test").version is None
    session.get.side_effect = None
    session.get.return_value = None
    with pytest.raises(Exception) as failure:
        get_profile(session, "agt_missing")
    assert failure.value.status_code == 404


@pytest.mark.parametrize(
    "label,values,expected_delay",
    [
        ("persistent LAN degradation", [100, 100, 100, 100, 100], 15),
        ("short application interruption", [False, True, True, True, True], 0),
        ("isolated spike", [100, 5, 5, 5, 5], None),
        ("tolerated oscillation", [49, 51, 49, 51, 49], None),
        ("tool errors", ["error"] * 5, None),
    ],
)
def test_labeled_scenarios_measure_confirmation_delay_without_false_alerts(
    label, values, expected_delay
):
    state = {}
    first_alert = None
    metric = (
        "network.https_success"
        if label == "short application interruption"
        else "network.gateway_latency_ms"
    )
    for index, value in enumerate(values):
        changes = (
            {"https_success": value}
            if label == "short application interruption"
            else {"gateway_collection_error": "ping missing"}
            if value == "error"
            else {"gateway_latency_ms": value}
        )
        state = step(state, index * 5, **changes)
        if rule(state, metric)["status"] == "active" and first_alert is None:
            first_alert = index * 5
    assert first_alert == expected_delay


def test_gap_during_hysteresis_does_not_add_unobserved_duration():
    state = {}
    for second in (0, 5, 10, 15):
        state = step(state, second, gateway_latency_ms=100)
    state = step(state, 100, gateway_latency_ms=45)
    state = step(state, 105, gateway_latency_ms=100)
    assert rule(state)["observed_duration_seconds"] == 15
    assert rule(state)["evidence_gap"] is True
