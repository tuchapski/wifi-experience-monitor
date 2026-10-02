from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session
from wifi_server.api.agents import router
from wifi_server.config import ServerSettings
from wifi_server.db.models import Agent, AgentCurrentState
from wifi_server.dependencies import get_session, get_settings
from wifi_server.schemas import AgentCurrentStateRequest, AgentCurrentStateResponse
from wifi_server.services.agents import update_current_state
from wifi_server.services.client_experience import evaluate_client_experience

NOW = datetime(2026, 10, 2, 17, tzinfo=UTC)


def snapshot(*, metadata=True, network=None, errors=None):
    wifi = {"connected": True, "interface": "wlan0", "rssi_dbm": -60}
    values = {
        "gateway": "192.0.2.1",
        "gateway_reachable": True,
        "gateway_latency_ms": 5,
        "gateway_packet_loss_percent": 0,
        "dns_success": True,
        "dns_latency_ms": 10,
        "internet_reachable": True,
        "https_success": True,
        "https_total_ms": 50,
        **(network or {}),
    }
    timings = (
        {
            f"{prefix}.{key}": {
                "observed_at": NOW,
                "source": "test",
                "sample_count": 1,
                "labels": {
                    "interface": "wlan0",
                    "target": "192.0.2.1" if key.startswith("gateway_") else "example.com",
                },
            }
            for prefix, data in (("wifi", wifi), ("network", values))
            for key in data
        }
        if metadata
        else {}
    )
    return AgentCurrentStateResponse(
        agent_id="agt_test",
        observed_at=NOW,
        updated_at=NOW,
        wifi=wifi,
        network=values,
        measurement_metadata=timings,
        collector_errors=errors or [],
    )


def evaluate(state, *, online=True, now=NOW):
    return evaluate_client_experience("agt_test", state, online=online, now=now)


def domain(result, name):
    return next(item for item in result.domains if item.domain == name)


def test_current_boolean_outcomes_certify_only_availability_and_preserve_zero_latency():
    result = evaluate(snapshot(network={"dns_latency_ms": 0}))
    assert result.status == "observed_ok"
    assert result.current_outcomes == 5
    assert result.outcome_coverage_percent == 100
    assert domain(result, "dns").measurements[1].value == 0
    assert domain(result, "local_network").target == "192.0.2.1"


def test_application_failure_cannot_be_hidden_by_four_successes():
    result = evaluate(snapshot(network={"https_success": False, "https_total_ms": None}))
    assert result.status == "failure"
    assert result.current_outcomes == 5
    assert domain(result, "application").status == "failure"
    assert domain(result, "wifi_rf").status == "observed_ok"


@pytest.mark.parametrize("loss,reachable,status", [(25, True, "degraded"), (100, False, "failure")])
def test_packet_loss_is_observed_degradation_not_collection_error(loss, reachable, status):
    result = evaluate(
        snapshot(network={"gateway_reachable": reachable, "gateway_packet_loss_percent": loss})
    )
    assert domain(result, "local_network").status == result.status == status


def test_old_probe_is_stale_even_when_wifi_snapshot_is_new():
    state = snapshot()
    state.measurement_metadata["network.https_success"].observed_at = NOW - timedelta(seconds=31)
    result = evaluate(state)
    assert domain(result, "application").status == "stale"
    assert result.status == "partial"
    assert result.current_outcomes == 4


@pytest.mark.parametrize("online,age", [(False, 0), (True, 31), (True, -6)])
def test_offline_stale_or_future_snapshot_cannot_certify_current_service(online, age):
    state = snapshot()
    state.observed_at = NOW - timedelta(seconds=age)
    result = evaluate(state, online=online)
    assert result.status == "stale"
    assert result.current_outcomes == 0


def test_legacy_outcomes_and_latency_only_remain_partial_or_unavailable():
    legacy = evaluate(snapshot(metadata=False))
    assert legacy.status == "partial"
    assert legacy.current_outcomes == 0
    assert domain(legacy, "wifi_rf").measurements[0].quality == "legacy"
    state = snapshot(network={"https_success": None})
    result = evaluate(state)
    assert domain(result, "application").status == "unavailable"
    assert domain(result, "application").measurements[1].value == 50


def test_persisted_tool_error_overrides_false_or_cached_success_without_poisoning_other_domains():
    state = snapshot(network={"dns_success": False, "dns_collection_error": "getent missing"})
    result = evaluate(state)
    assert domain(result, "dns").status == "collection_error"
    assert domain(result, "application").status == "observed_ok"
    assert result.status == "partial"
    assert result.current_outcomes == 4
    assert domain(result, "dns").measurements[-1].value == "getent missing"
    state = snapshot(errors=["gateway ping collection failed: Operation not permitted"])
    assert domain(evaluate(state), "local_network").status == "collection_error"


@pytest.mark.parametrize("kind", ["future", "interface", "target", "numeric_outcome"])
def test_invalid_clock_or_changed_context_does_not_produce_healthy_domain(kind):
    state = snapshot()
    meta = state.measurement_metadata["network.gateway_reachable"]
    if kind == "future":
        meta.observed_at = NOW + timedelta(seconds=6)
    elif kind == "interface":
        meta.labels["interface"] = "wlan1"
    elif kind == "target":
        meta.labels["target"] = "192.0.2.99"
    else:
        state.network.model_extra["gateway_reachable"] = 1
    result = evaluate(state)
    assert domain(result, "local_network").status == "partial"
    assert result.current_outcomes == 4


def test_non_finite_values_are_omitted_from_serializable_evidence():
    state = snapshot(network={"gateway_latency_ms": float("nan")})
    result = evaluate(state)
    measurement = domain(result, "local_network").measurements[1]
    assert measurement.value is None
    assert measurement.quality == "invalid"
    assert "NaN" not in result.model_dump_json()


def test_measurement_metadata_is_persisted_and_roundtripped_without_database_migration():
    state = snapshot()
    request = AgentCurrentStateRequest(**state.model_dump(exclude={"agent_id", "updated_at"}))
    session = Mock(spec=Session)
    session.get.return_value = None
    response = update_current_state(session, Agent(id="agt_test"), request)
    record = session.add.call_args.args[0]
    assert record.raw_state["measurement_metadata"]["network.dns_success"]["source"] == "test"
    assert response.measurement_metadata["network.dns_success"].observed_at == NOW
    with pytest.raises(ValidationError):
        AgentCurrentStateRequest(
            observed_at=NOW,
            measurement_metadata={
                "network.dns_success": {"observed_at": NOW.replace(tzinfo=None), "source": "test"},
            },
        )


def test_endpoint_missing_agent_or_state_and_online_snapshot():
    session = Mock(spec=Session)
    agent = Agent(id="agt_test", last_seen_at=NOW)
    raw = snapshot().model_dump(mode="json", exclude={"agent_id", "updated_at", "observed_at"})
    current = AgentCurrentState(agent_id="agt_test", observed_at=NOW, updated_at=NOW, raw_state=raw)
    session.get.side_effect = lambda model, _id: agent if model is Agent else current
    settings = ServerSettings("postgresql://unused", Path("/tmp"), None, 15, 24)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    with (
        patch("wifi_server.services.client_experience.datetime") as clock,
        TestClient(app) as client,
    ):
        clock.now.return_value = NOW
        response = client.get("/api/v1/agents/agt_test/experience")
        assert response.status_code == 200
        assert response.json()["status"] == "observed_ok"
        current = None
        response = client.get("/api/v1/agents/agt_test/experience")
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"
        agent = None
        assert client.get("/api/v1/agents/missing/experience").status_code == 404
