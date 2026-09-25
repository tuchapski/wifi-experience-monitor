"""Describe measurements around BSSID transitions without inferring their cause."""

from datetime import timedelta
from statistics import median
from typing import Any

from wifi_server.analysis.recording import (
    MetricSample,
    RecordingAnalysisResult,
    StateEvent,
)
from wifi_server.analysis.recording_v4 import analyze_recording as analyze_recording_v4

ENGINE_VERSION = "recording-analysis-v5"
WINDOW_SECONDS = 10
MIN_SAMPLES_PER_SIDE = 3
MAX_NEAREST_SAMPLE_SECONDS = 3
COMPARISON_METRICS = (
    "wifi.rssi_dbm",
    "wifi.tx_retries_per_100_packets",
    "wifi.channel_utilization_percent",
)


def _transitions(metrics: list[MetricSample], events: list[StateEvent]) -> list[dict[str, Any]]:
    ordered = sorted(events, key=lambda event: event.observed_at)
    by_metric = {
        key: sorted(
            (sample for sample in metrics if sample.metric == key),
            key=lambda sample: sample.observed_at,
        )
        for key in COMPARISON_METRICS
    }
    transitions: list[dict[str, Any]] = []
    for event in ordered:
        if event.event_type != "state.changed" or event.data.get("metric") != "wifi.bssid":
            continue
        previous, current = event.data.get("previous"), event.data.get("current")
        if not isinstance(previous, str) or not previous:
            continue
        if not isinstance(current, str) or not current:
            continue
        if previous == current:
            continue

        at = event.observed_at
        start = at - timedelta(seconds=WINDOW_SECONDS)
        end = at + timedelta(seconds=WINDOW_SECONDS)
        interference = [
            other
            for other in ordered
            if other is not event
            and start <= other.observed_at <= end
            and other.event_type == "state.changed"
            and other.data.get("metric") in {"wifi.bssid", "wifi.ssid", "wifi.connected"}
        ]
        reasons: list[str] = []
        if interference:
            reasons.append(
                "Another association, SSID or connectivity change occurred "
                "in the comparison window."
            )
        comparison: dict[str, Any] = {}
        for key, samples in by_metric.items():
            before = [sample for sample in samples if start <= sample.observed_at < at]
            after = [sample for sample in samples if at < sample.observed_at <= end]
            sufficient = (
                len(before) >= MIN_SAMPLES_PER_SIDE
                and len(after) >= MIN_SAMPLES_PER_SIDE
                and (at - before[-1].observed_at).total_seconds() <= MAX_NEAREST_SAMPLE_SECONDS
                and (after[0].observed_at - at).total_seconds() <= MAX_NEAREST_SAMPLE_SECONDS
            )
            before_median: float | None = None
            after_median: float | None = None
            if sufficient:
                before_median = round(median(sample.value for sample in before), 2)
                after_median = round(median(sample.value for sample in after), 2)
            comparison[key] = {
                "before_samples": len(before),
                "after_samples": len(after),
                "before_median": before_median,
                "after_median": after_median,
                "delta": (
                    round(after_median - before_median, 2)
                    if before_median is not None and after_median is not None
                    else None
                ),
            }

        if not any(item["delta"] is not None for item in comparison.values()):
            reasons.append("No metric had enough nearby samples on both sides of the change.")
        transitions.append(
            {
                "observed_at": at.isoformat(),
                "previous_bssid": previous,
                "current_bssid": current,
                "comparison_seconds": WINDOW_SECONDS,
                "status": "limited" if reasons else "comparable",
                "limitations": reasons,
                "metrics": comparison,
            }
        )
    return transitions


def analyze_recording(
    metrics: list[MetricSample], events: list[StateEvent]
) -> RecordingAnalysisResult:
    base = analyze_recording_v4(metrics, events)
    summary = dict(base.summary)
    summary["bssid_transitions"] = _transitions(metrics, events)
    policy = dict(base.policy)
    policy["version"] = ENGINE_VERSION
    policy["bssid_comparison"] = {
        "window_seconds_each_side": WINDOW_SECONDS,
        "minimum_samples_per_side": MIN_SAMPLES_PER_SIDE,
        "maximum_nearest_sample_seconds": MAX_NEAREST_SAMPLE_SECONDS,
        "metrics": list(COMPARISON_METRICS),
    }
    policy["notes"] = [
        *list(base.policy.get("notes", [])),
        ("BSSID transitions are observed association changes, not proof of 802.11 roaming."),
        (
            "Before/after medians are descriptive; different channels and background "
            "traffic may make utilization and retry values differ independently "
            "of the transition."
        ),
    ]
    return RecordingAnalysisResult(summary=summary, findings=base.findings, policy=policy)
