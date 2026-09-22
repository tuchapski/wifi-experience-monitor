import json
import math
from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient

from wem.analysis.experience import (
    COMPONENT_WEIGHTS,
    CONNECTIVITY_RULES,
    MINIMUM_COVERAGE,
    WIFI_RULES,
    ExperienceScoreEngine,
    interpolate,
    metric,
)
from wem.api.app import create_app
from wem.models.metrics import (
    CalibrationResult,
    ConnectivityMetrics,
    NetworkMetrics,
    SensorHealthMetrics,
    SensorSnapshot,
    WifiDeltaMetrics,
    WifiMetrics,
)
from wem.models.metrics import (
    TestOutcome as Outcome,
)
from wem.storage.database import Database
from wem.storage.repository import SnapshotRepository


@pytest.fixture
def inputs():
    return {
        "wifi": WifiMetrics("wlan0", associated=True, signal_dbm=-60),
        "wifi_delta": WifiDeltaMetrics(
            interval_seconds=5,
            tx_packets_delta=100,
            tx_retries_per_100_packets=5,
            tx_failed_percent=0,
        ),
        "connectivity": ConnectivityMetrics(
            tests={
                key: Outcome(
                    "passed",
                    "Test passed",
                    "host" if key in {"dns", "https"} else "selected_interface",
                )
                for key in CONNECTIVITY_RULES
            },
            gateway_reachable=True,
            gateway_latency_avg_ms=5,
            gateway_packet_loss_percent=0,
            internet_reachable=True,
            internet_latency_avg_ms=30,
            internet_packet_loss_percent=0,
            dns_success=True,
            dns_latency_ms=10,
            https_success=True,
            https_total_time_ms=100,
            https_status_code=200,
        ),
        "calibration": CalibrationResult(status="ok", calibrated=True),
        "collector_errors": [],
    }


def calculate(inputs):
    return ExperienceScoreEngine().calculate(**inputs)


def component(result, key):
    return next(item for item in result.components if item.key == key)


def test_healthy_full_coverage_and_weights(inputs):
    result = calculate(inputs)
    assert sum(COMPONENT_WEIGHTS.values()) == 100
    for rules in (WIFI_RULES, *CONNECTIVITY_RULES.values()):
        assert sum(rule.weight for rule in rules) == 100
    assert result.value == 100
    assert result.status == "complete"
    assert result.coverage_percent == 100
    assert result.policy_version == "experience-v1"
    assert sum(item.contribution for item in result.components) == 100
    assert sum(item.deduction for item in result.components) == 0
    assert component(result, "dns").scope == "host"


ALL_RULES = [*WIFI_RULES, *(rule for rules in CONNECTIVITY_RULES.values() for rule in rules)]


@pytest.mark.parametrize("rule", ALL_RULES)
def test_policy_anchors_interpolation_and_monotonicity(rule):
    for value, expected in rule.anchors:
        assert interpolate(value, rule) == expected
        assert metric(rule, value).score == expected
    for (left, a), (right, b) in zip(rule.anchors, rule.anchors[1:], strict=False):
        assert interpolate((left + right) / 2, rule) == pytest.approx((a + b) / 2)
    values = [
        rule.anchors[0][0] + n * (rule.anchors[-1][0] - rule.anchors[0][0]) / 100
        for n in range(101)
    ]
    scores = [interpolate(value, rule) for value in values]
    assert all(0 <= score <= 100 for score in scores)
    assert scores == sorted(scores, reverse=rule.key != "rssi")


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1, True])
def test_missing_and_invalid_latency_is_not_zero(value):
    item = metric(CONNECTIVITY_RULES["dns"][0], value)
    assert item.score is None
    assert item.value is None
    assert item.state == "unavailable"


def test_invalid_rssi_and_loss_are_excluded():
    assert metric(WIFI_RULES[0], 0).score is None
    assert metric(WIFI_RULES[0], -128).score is None
    assert metric(CONNECTIVITY_RULES["gateway"][1], 101).score is None
    assert metric(WIFI_RULES[1], 300).score == 0  # Retry ratios can exceed 100.


def test_penalties_have_exact_weighted_contributions(inputs):
    inputs["wifi"].signal_dbm = -75  # RSSI 70, component 88.
    inputs["connectivity"].gateway_packet_loss_percent = 5  # loss 60, component 76.
    result = calculate(inputs)
    assert component(result, "wifi").score == 88
    assert component(result, "wifi").contribution == 26.4
    assert component(result, "wifi").deduction == 3.6
    assert component(result, "gateway").score == 76
    assert result.value == 91.6
    assert sum(part.contribution for part in result.components) == pytest.approx(result.value)
    assert sum(part.deduction for part in result.components) == pytest.approx(8.4)


@pytest.mark.parametrize(
    "key,flag",
    [
        ("gateway", "gateway_reachable"),
        ("internet", "internet_reachable"),
        ("dns", "dns_success"),
        ("https", "https_success"),
    ],
)
def test_confirmed_failure_counts_as_evidence_not_missing(inputs, key, flag):
    data = inputs["connectivity"]
    data.tests[key] = Outcome("failed", "Confirmed failure", "host")
    setattr(data, flag, False)
    result = calculate(inputs)
    item = component(result, key)
    assert item.score == 0
    assert item.coverage_percent == 100
    assert all(m.value is None and m.state == "failed" for m in item.metrics)
    assert result.value == 100 - COMPONENT_WEIGHTS[key]
    assert result.status == "complete"  # Complete evidence, not all tests passed!
    if key in {"gateway", "internet"}:
        assert "not proof" in item.metrics[0].reason


@pytest.mark.parametrize("state", ["error", "skipped", "unavailable", "observed"])
def test_bad_collection_outcome_overrides_numeric_values(inputs, state):
    inputs["connectivity"].tests["dns"] = Outcome(state, "Measurement not usable")
    inputs["connectivity"].dns_success = False
    inputs["connectivity"].dns_latency_ms = 0
    result = calculate(inputs)
    assert result.value == 100
    assert result.status == "partial"
    assert result.coverage_percent == 85
    assert component(result, "dns").score is None
    assert component(result, "dns").deduction is None
    assert component(result, "wifi").effective_weight == pytest.approx(30 / 85 * 100, abs=0.0001)


@pytest.mark.parametrize("state,success", [("passed", False), ("failed", True), ("passed", None)])
def test_contradictory_test_outcome_is_not_used(inputs, state, success):
    inputs["connectivity"].tests["dns"] = Outcome(state, "Contradictory test")
    inputs["connectivity"].dns_success = success
    assert component(calculate(inputs), "dns").score is None


def test_first_sample_and_no_tx_traffic_have_partial_wifi(inputs):
    inputs["wifi_delta"] = None
    result = calculate(inputs)
    assert result.value == 100
    assert result.status == "partial"
    assert result.coverage_percent == 82  # RSSI 12 + connectivity 70.
    assert component(result, "wifi").coverage_percent == 40
    assert "renormalized" in " ".join(result.reasons)


@pytest.mark.parametrize(
    "change",
    [
        "idle",
        "reset",
        "roam",
        "reason",
        "zero_interval",
        "nonfinite_interval",
        "missing_interval",
    ],
)
def test_unreliable_delta_never_produces_counter_score(inputs, change):
    delta = inputs["wifi_delta"]
    if change == "idle":
        delta.tx_packets_delta = 0
    elif change == "reset":
        delta.counter_reset_detected = True
    elif change == "roam":
        delta.association_changed = True
    elif change == "reason":
        delta.unavailable_reason = "Not comparable"
    elif change == "zero_interval":
        delta.interval_seconds = 0
    elif change == "missing_interval":
        delta.interval_seconds = None
    else:
        delta.interval_seconds = math.nan
    result = calculate(inputs)
    assert result.coverage_percent == 82
    assert component(result, "wifi").metrics[1].score is None
    assert component(result, "wifi").metrics[2].score is None


def test_no_data_is_unavailable_not_healthy():
    result = ExperienceScoreEngine().calculate(
        WifiMetrics("wlan0"),
        None,
        ConnectivityMetrics(),
        None,
    )
    assert result.value is None
    assert result.coverage_percent == 0
    assert result.status == "unavailable"
    assert all(part.score is None for part in result.components)
    assert all(part.effective_weight == 0 for part in result.components)


def test_global_requires_wifi_even_with_70_percent_coverage(inputs):
    inputs["wifi"].associated = None
    result = calculate(inputs)
    assert result.coverage_percent == MINIMUM_COVERAGE
    assert result.value is None
    assert result.status == "unavailable"
    assert component(result, "dns").score == 100
    assert component(result, "dns").contribution is None


def test_minimum_coverage_boundary(inputs):
    for key in ("dns", "https"):
        inputs["connectivity"].tests[key] = Outcome("skipped", "Disabled")
    result = calculate(inputs)
    assert result.coverage_percent == 70
    assert result.value == 100
    assert result.status == "partial"
    inputs["wifi_delta"].tx_failed_percent = None
    result = calculate(inputs)
    assert result.coverage_percent == 64
    assert result.value is None


def test_disconnected_wifi_is_zero_without_fabricated_downstream_failures(inputs):
    inputs["wifi"].associated = False
    for key in CONNECTIVITY_RULES:
        inputs["connectivity"].tests[key] = Outcome("skipped", "Not associated")
    result = calculate(inputs)
    assert component(result, "wifi").score == 0
    assert component(result, "wifi").coverage_percent == 100
    assert result.coverage_percent == 30
    assert result.value is None
    assert all(part.score is None for part in result.components[1:])


@pytest.mark.parametrize("calibration", [None, CalibrationResult("warning", False)])
def test_calibration_uncertainty_prevents_complete_label(inputs, calibration):
    inputs["calibration"] = calibration
    result = calculate(inputs)
    assert result.value == 100
    assert result.coverage_percent == 100
    assert result.status == "partial"
    assert "calibration" in " ".join(result.reasons)


def test_collection_errors_do_not_penalize_valid_evidence(inputs):
    inputs["collector_errors"] = ["Unable to inspect firmware"]
    result = calculate(inputs)
    assert result.value == 100
    assert result.status == "partial"
    assert "Collection errors" in " ".join(result.reasons)


def test_optional_rf_support_does_not_change_score(inputs):
    before = calculate(inputs)
    inputs["wifi"].survey.status = "unsupported"
    inputs["wifi"].survey.reason = "Not supported"
    assert calculate(inputs) == before


def test_old_measurements_without_explicit_outcomes_are_not_trusted(inputs):
    inputs["connectivity"].tests = {}
    result = calculate(inputs)
    assert result.coverage_percent == 30
    assert result.value is None


def test_extreme_valid_values_remain_bounded_and_serializable(inputs):
    inputs["wifi"].signal_dbm = -127
    inputs["wifi_delta"].tx_retries_per_100_packets = 300
    inputs["wifi_delta"].tx_failed_percent = 150
    inputs["connectivity"].dns_latency_ms = 1e10
    result = calculate(inputs)
    assert 0 <= result.value <= 100
    assert component(result, "wifi").score == 0
    json.dumps(asdict(result), allow_nan=False)


def test_round_trip_api_and_legacy_snapshot(inputs, tmp_path):
    database_path = str(tmp_path / "score.db")
    database = Database(database_path)
    database.initialize()
    repository = SnapshotRepository(database)
    score = calculate(inputs)
    snapshot = SensorSnapshot.create(
        health=SensorHealthMetrics("wlan0"),
        calibration=inputs["calibration"],
        wifi=inputs["wifi"],
        wifi_delta=inputs["wifi_delta"],
        network=NetworkMetrics("wlan0"),
        connectivity=inputs["connectivity"],
        experience_score=score,
    )
    repository.save(snapshot)
    with TestClient(create_app(database_path)) as client:
        response = client.get("/snapshot/latest")
        assert response.status_code == 200
        assert response.json()["experience_score"] == asdict(score)

    # An old JSON payload has no score; the API must not invent or recompute it.
    old_payload = replace(snapshot, experience_score=None).to_dict()
    old_payload.pop("experience_score")
    record = repository.latest_one()
    with database.session() as session:
        stored = session.get(type(record), record.id)
        stored.snapshot_json = json.dumps(old_payload)
        session.commit()
    with TestClient(create_app(database_path)) as client:
        assert "experience_score" not in client.get("/snapshot/latest").json()
