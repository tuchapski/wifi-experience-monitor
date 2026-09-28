from datetime import UTC, datetime, timedelta

from wifi_server.analysis.recording import MetricSample
from wifi_server.analysis.recording_v8 import analyze_recording

START = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def sample(second: int, metric: str, value: float) -> MetricSample:
    return MetricSample(START + timedelta(seconds=second), metric, value)


def series(metric: str, baseline: float, degraded: float | None = None) -> list[MetricSample]:
    samples = [sample(second, metric, baseline) for second in range(0, 30, 5)]
    if degraded is not None:
        samples.extend(sample(second, metric, degraded) for second in (60, 65, 70))
        samples.extend(sample(second, metric, baseline) for second in (75, 80))
    return samples


def analyze(metrics: list[MetricSample]):
    return analyze_recording(
        metrics,
        [],
        started_at=START,
        ended_at=START + timedelta(seconds=90),
    )


def test_cross_layer_episode_groups_propagated_degradation() -> None:
    metrics = [
        *series("wifi.rssi_dbm", -55.0, -75.0),
        *series("network.gateway_latency_ms", 3.0, 40.0),
        *series("network.dns_latency_ms", 3.0, 4.0),
        *series("network.internet_latency_ms", 20.0, 90.0),
        *series("network.https_total_ms", 50.0, 220.0),
    ]

    result = analyze(metrics)

    assert result.policy["version"] == "recording-analysis-v8"
    assert result.summary["cross_layer_episode_summary"] == {
        "total": 1,
        "single_domain": 0,
        "cross_layer": 1,
        "baseline_metrics": 5,
        "unavailable_baseline_metrics": [],
    }
    episode = result.summary["cross_layer_episodes"][0]
    assert episode["trigger_domain"] == "wifi_rf"
    assert episode["trigger_metric"] == "wifi.rssi_dbm"
    assert episode["observed_domains"] == [
        "wifi_rf",
        "local_network",
        "internet",
        "application",
    ]
    assert episode["scope"] == "cross_layer"
    assert episode["recovery_confirmed"] is True
    assert "dns" not in episode["domain_evidence"]


def test_internet_only_degradation_creates_episode_without_wifi_trigger() -> None:
    metrics = [
        *series("wifi.rssi_dbm", -55.0),
        *series("network.gateway_latency_ms", 3.0),
        *series("network.dns_latency_ms", 3.0),
        *series("network.internet_latency_ms", 20.0, 90.0),
        *series("network.https_total_ms", 50.0),
    ]
    metrics.extend(sample(second, "wifi.rssi_dbm", -55.0) for second in (60, 65, 70, 75, 80))
    metrics.extend(
        sample(second, "network.gateway_latency_ms", 3.0) for second in (60, 65, 70, 75, 80)
    )
    metrics.extend(sample(second, "network.dns_latency_ms", 3.0) for second in (60, 65, 70, 75, 80))
    metrics.extend(
        sample(second, "network.https_total_ms", 50.0) for second in (60, 65, 70, 75, 80)
    )

    result = analyze(metrics)

    assert len(result.summary["cross_layer_episodes"]) == 1
    episode = result.summary["cross_layer_episodes"][0]
    assert episode["trigger_domain"] == "internet"
    assert episode["observed_domains"] == ["internet"]
    assert episode["scope"] == "single_domain"


def test_dns_only_degradation_is_detected_as_independent_episode() -> None:
    metrics = [
        *series("network.dns_latency_ms", 3.0, 80.0),
        *series("network.internet_latency_ms", 20.0),
    ]
    metrics.extend(
        sample(second, "network.internet_latency_ms", 20.0) for second in (60, 65, 70, 75, 80)
    )

    result = analyze(metrics)

    episode = result.summary["cross_layer_episodes"][0]
    assert episode["trigger_domain"] == "dns"
    assert episode["observed_domains"] == ["dns"]


def test_nearby_domain_degradations_merge_into_one_episode() -> None:
    metrics = [
        *series("wifi.rssi_dbm", -55.0),
        *series("network.gateway_latency_ms", 3.0),
    ]
    metrics.extend(sample(second, "wifi.rssi_dbm", -75.0) for second in (60, 65, 70))
    metrics.extend(sample(second, "wifi.rssi_dbm", -55.0) for second in (75, 80))
    metrics.extend(sample(second, "network.gateway_latency_ms", 40.0) for second in (85, 90, 95))
    metrics.extend(sample(second, "network.gateway_latency_ms", 3.0) for second in (100, 105))

    result = analyze_recording(
        metrics,
        [],
        started_at=START,
        ended_at=START + timedelta(seconds=110),
    )

    assert len(result.summary["cross_layer_episodes"]) == 1
    episode = result.summary["cross_layer_episodes"][0]
    assert episode["trigger_domain"] == "wifi_rf"
    assert episode["observed_domains"] == ["wifi_rf", "local_network"]
    assert episode["scope"] == "cross_layer"


def test_metric_without_initial_baseline_does_not_create_false_episode() -> None:
    metrics = [
        sample(60, "network.internet_latency_ms", 90.0),
        sample(65, "network.internet_latency_ms", 95.0),
        sample(70, "network.internet_latency_ms", 100.0),
    ]

    result = analyze(metrics)

    assert result.summary["cross_layer_episodes"] == []
    assert result.summary["cross_layer_episode_summary"]["baseline_metrics"] == 0
    assert result.summary["cross_layer_episode_summary"]["unavailable_baseline_metrics"] == [
        "network.internet_latency_ms"
    ]


def test_episode_without_recovery_samples_is_marked_unconfirmed() -> None:
    metrics = [
        *series("network.internet_latency_ms", 20.0),
        sample(60, "network.internet_latency_ms", 90.0),
        sample(65, "network.internet_latency_ms", 95.0),
        sample(70, "network.internet_latency_ms", 100.0),
    ]

    result = analyze(metrics)

    episode = result.summary["cross_layer_episodes"][0]
    assert episode["recovery_confirmed"] is False
