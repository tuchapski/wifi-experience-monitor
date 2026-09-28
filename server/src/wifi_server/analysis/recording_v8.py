"""Detect sustained diagnostic episodes across Wi-Fi, network and service evidence domains."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from statistics import median
from typing import Any

from wifi_server.analysis.recording import MetricSample, RecordingAnalysisResult, StateEvent
from wifi_server.analysis.recording_v7 import analyze_recording as analyze_recording_v7
from wifi_server.diagnostic_policy import (
    EVIDENCE_DOMAIN_ORDER,
    FINDING_RULES,
    METRIC_EVIDENCE_DOMAIN,
)

ENGINE_VERSION = "recording-analysis-v8"
BASELINE_WINDOW_SECONDS = 30
MIN_BASELINE_SAMPLES = 3
MIN_DEGRADED_SAMPLES = 3
RECOVERY_SAMPLES = 2
MAX_METRIC_GAP_SECONDS = 7.5
EPISODE_MERGE_GAP_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class MetricDegradationInterval:
    metric: str
    domain: str
    started_at: datetime
    ended_at: datetime
    degraded_samples: int
    peak_delta: float
    recovery_confirmed: bool


def _deterioration_delta(value: float, baseline: float, metric: str) -> float | None:
    rule = FINDING_RULES.get(metric)
    if rule is None:
        return None
    threshold, direction = rule
    delta = value - baseline
    deteriorated = delta <= -threshold if direction == "decrease" else delta >= threshold
    return delta if deteriorated else None


def _peak_delta(current: float, candidate: float) -> float:
    return candidate if abs(candidate) > abs(current) else current


def _metric_intervals(
    metric: str,
    samples: list[MetricSample],
    baseline: float,
    baseline_end: datetime,
) -> list[MetricDegradationInterval]:
    domain = METRIC_EVIDENCE_DOMAIN[metric]
    ordered = sorted(
        (
            sample
            for sample in samples
            if sample.metric == metric
            and sample.observed_at >= baseline_end
            and isfinite(sample.value)
        ),
        key=lambda sample: sample.observed_at,
    )
    intervals: list[MetricDegradationInterval] = []
    candidate: list[tuple[MetricSample, float]] = []
    active: dict[str, Any] | None = None
    previous_at: datetime | None = None
    recovery_run = 0

    def close(ended_at: datetime, recovery_confirmed: bool) -> None:
        nonlocal active, candidate, recovery_run
        if active is not None:
            intervals.append(
                MetricDegradationInterval(
                    metric=metric,
                    domain=domain,
                    started_at=active["started_at"],
                    ended_at=ended_at,
                    degraded_samples=active["degraded_samples"],
                    peak_delta=round(active["peak_delta"], 3),
                    recovery_confirmed=recovery_confirmed,
                )
            )
        active = None
        candidate = []
        recovery_run = 0

    for sample in ordered:
        if (
            previous_at is not None
            and (sample.observed_at - previous_at).total_seconds() > MAX_METRIC_GAP_SECONDS
        ):
            if active is not None:
                close(active["last_degraded_at"], recovery_confirmed=False)
            else:
                candidate = []
        previous_at = sample.observed_at

        delta = _deterioration_delta(sample.value, baseline, metric)
        if delta is not None:
            recovery_run = 0
            if active is None:
                candidate.append((sample, delta))
                if len(candidate) < MIN_DEGRADED_SAMPLES:
                    continue
                active = {
                    "started_at": candidate[0][0].observed_at,
                    "last_degraded_at": sample.observed_at,
                    "degraded_samples": len(candidate),
                    "peak_delta": max(candidate, key=lambda item: abs(item[1]))[1],
                }
                candidate = []
                continue

            active["last_degraded_at"] = sample.observed_at
            active["degraded_samples"] += 1
            active["peak_delta"] = _peak_delta(active["peak_delta"], delta)
            continue

        if active is None:
            candidate = []
            continue

        recovery_run += 1
        if recovery_run >= RECOVERY_SAMPLES:
            close(sample.observed_at, recovery_confirmed=True)

    if active is not None:
        close(active["last_degraded_at"], recovery_confirmed=False)
    return intervals


def _baselines(
    metrics: list[MetricSample],
    started_at: datetime | None,
) -> tuple[dict[str, float], datetime | None, list[str]]:
    relevant = [
        sample for sample in metrics if sample.metric in FINDING_RULES and isfinite(sample.value)
    ]
    if not relevant:
        return {}, None, []

    baseline_start = started_at or min(sample.observed_at for sample in relevant)
    baseline_end = baseline_start + timedelta(seconds=BASELINE_WINDOW_SECONDS)
    observed_metrics = sorted({sample.metric for sample in relevant})
    values: dict[str, list[float]] = {metric: [] for metric in observed_metrics}
    for sample in relevant:
        if baseline_start <= sample.observed_at < baseline_end:
            values[sample.metric].append(sample.value)

    baselines = {
        metric: round(float(median(samples)), 3)
        for metric, samples in values.items()
        if len(samples) >= MIN_BASELINE_SAMPLES
    }
    unavailable = [metric for metric in observed_metrics if metric not in baselines]
    return baselines, baseline_end, unavailable


def _episodes(
    intervals: list[MetricDegradationInterval],
    baselines: dict[str, float],
) -> list[dict[str, Any]]:
    domain_rank = {domain: index for index, domain in enumerate(EVIDENCE_DOMAIN_ORDER)}
    ordered = sorted(
        intervals,
        key=lambda item: (
            item.started_at,
            domain_rank.get(item.domain, len(domain_rank)),
            item.metric,
        ),
    )
    groups: list[list[MetricDegradationInterval]] = []
    current: list[MetricDegradationInterval] = []
    current_end: datetime | None = None

    for interval in ordered:
        if (
            current
            and current_end is not None
            and interval.started_at > current_end + timedelta(seconds=EPISODE_MERGE_GAP_SECONDS)
        ):
            groups.append(current)
            current = []
            current_end = None
        current.append(interval)
        current_end = (
            interval.ended_at if current_end is None else max(current_end, interval.ended_at)
        )
    if current:
        groups.append(current)

    episodes: list[dict[str, Any]] = []
    for group in groups:
        started = min(item.started_at for item in group)
        ended = max(item.ended_at for item in group)
        first = min(
            group,
            key=lambda item: (
                item.started_at,
                domain_rank.get(item.domain, len(domain_rank)),
                item.metric,
            ),
        )
        domains = [
            domain
            for domain in EVIDENCE_DOMAIN_ORDER
            if any(item.domain == domain for item in group)
        ]
        domain_evidence = {
            domain: sorted({item.metric for item in group if item.domain == domain})
            for domain in domains
        }
        peak_deltas: dict[str, float] = {}
        for item in group:
            existing = peak_deltas.get(item.metric)
            if existing is None or abs(item.peak_delta) > abs(existing):
                peak_deltas[item.metric] = item.peak_delta

        episodes.append(
            {
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "duration_seconds": round(max(0.0, (ended - started).total_seconds()), 2),
                "trigger_domain": first.domain,
                "trigger_metric": first.metric,
                "observed_domains": domains,
                "scope": "cross_layer" if len(domains) > 1 else "single_domain",
                "metrics": sorted({item.metric for item in group}),
                "degraded_samples": sum(item.degraded_samples for item in group),
                "recovery_confirmed": all(item.recovery_confirmed for item in group),
                "domain_evidence": domain_evidence,
                "peak_deltas": {metric: round(delta, 3) for metric, delta in peak_deltas.items()},
                "baselines": {
                    metric: baselines[metric]
                    for metric in sorted({item.metric for item in group})
                    if metric in baselines
                },
            }
        )
    return episodes


def _cross_layer_episodes(
    metrics: list[MetricSample],
    started_at: datetime | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baselines, baseline_end, unavailable = _baselines(metrics, started_at)
    if baseline_end is None:
        return [], {
            "total": 0,
            "single_domain": 0,
            "cross_layer": 0,
            "baseline_metrics": 0,
            "unavailable_baseline_metrics": [],
        }

    intervals = [
        interval
        for metric, baseline in baselines.items()
        for interval in _metric_intervals(metric, metrics, baseline, baseline_end)
    ]
    episodes = _episodes(intervals, baselines)
    return episodes, {
        "total": len(episodes),
        "single_domain": sum(item["scope"] == "single_domain" for item in episodes),
        "cross_layer": sum(item["scope"] == "cross_layer" for item in episodes),
        "baseline_metrics": len(baselines),
        "unavailable_baseline_metrics": unavailable,
    }


def analyze_recording(
    metrics: list[MetricSample],
    events: list[StateEvent],
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> RecordingAnalysisResult:
    base = analyze_recording_v7(
        metrics,
        events,
        started_at=started_at,
        ended_at=ended_at,
    )
    summary = dict(base.summary)
    episodes, episode_summary = _cross_layer_episodes(metrics, started_at)
    summary["cross_layer_episodes"] = episodes
    summary["cross_layer_episode_summary"] = episode_summary
    if episodes and summary["status"] == "clear":
        summary["status"] = "observed"

    limitations = list(summary.get("limitations", []))
    if episode_summary["unavailable_baseline_metrics"]:
        limitations.append(
            "Cross-layer episode detection could not establish an initial baseline for: "
            + ", ".join(episode_summary["unavailable_baseline_metrics"])
            + "."
        )
    if episode_summary["baseline_metrics"] > 0:
        limitations.append(
            "Cross-layer v1 uses the first 30 seconds as a fixed baseline; deterioration "
            "already present in that period may not be detected as an episode."
        )
    summary["limitations"] = limitations

    policy = dict(base.policy)
    policy["version"] = ENGINE_VERSION
    policy["cross_layer_episodes"] = {
        "baseline_window_seconds": BASELINE_WINDOW_SECONDS,
        "minimum_baseline_samples": MIN_BASELINE_SAMPLES,
        "minimum_degraded_samples": MIN_DEGRADED_SAMPLES,
        "recovery_samples": RECOVERY_SAMPLES,
        "max_metric_gap_seconds": MAX_METRIC_GAP_SECONDS,
        "episode_merge_gap_seconds": EPISODE_MERGE_GAP_SECONDS,
        "metric_rules": {
            metric: {"threshold": threshold, "direction": direction}
            for metric, (threshold, direction) in FINDING_RULES.items()
        },
    }
    policy["notes"] = [
        *list(base.policy.get("notes", [])),
        (
            "Cross-layer episodes group sustained relative deterioration across monitored "
            "evidence domains; they identify investigation intervals, not root cause."
        ),
        (
            "Episode trigger_domain is the earliest monitored degraded domain after the "
            "fixed initial baseline and is not a causal attribution."
        ),
        (
            "A cross-layer episode upgrades a clear recording assessment to observed; "
            "v8 does not assign warning or critical severity to episodes."
        ),
    ]
    return RecordingAnalysisResult(summary=summary, findings=base.findings, policy=policy)
