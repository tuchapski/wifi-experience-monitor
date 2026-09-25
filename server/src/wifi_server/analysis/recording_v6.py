"""Assess collection continuity using cycle markers captured by the Agent."""

from datetime import datetime
from math import isfinite
from typing import Any

from wifi_server.analysis.recording import MetricSample, RecordingAnalysisResult, StateEvent
from wifi_server.analysis.recording_v5 import analyze_recording as analyze_recording_v5

ENGINE_VERSION = "recording-analysis-v6"
CYCLE_METRIC = "sensor.collection_cycle"


def _continuity(
    metrics: list[MetricSample],
    started_at: datetime | None,
    ended_at: datetime | None,
) -> dict[str, Any]:
    cycles = sorted(
        (sample for sample in metrics if sample.metric == CYCLE_METRIC),
        key=lambda sample: sample.observed_at,
    )
    result: dict[str, Any] = {
        "status": "unavailable",
        "cycle_count": len(cycles),
        "configured_interval_seconds": None,
        "gap_threshold_seconds": None,
        "collector_error_cycles": 0,
        "gaps": [],
    }
    if not cycles or started_at is None or ended_at is None or ended_at < started_at:
        return result

    intervals = [sample.labels.get("configured_interval_seconds") for sample in cycles]
    errors = [sample.labels.get("collector_errors_count") for sample in cycles]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
        for value in intervals
    ):
        return result
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in errors):
        return result
    if any(value != intervals[0] for value in intervals):
        return result
    if any(sample.observed_at < started_at or sample.observed_at > ended_at for sample in cycles):
        return result

    interval = float(intervals[0])
    threshold = max(3 * interval, interval + 2)
    result["configured_interval_seconds"] = interval
    result["gap_threshold_seconds"] = round(threshold, 2)
    result["collector_error_cycles"] = sum(value > 0 for value in errors)

    timestamps = [started_at, *(sample.observed_at for sample in cycles), ended_at]
    for earlier, later in zip(timestamps, timestamps[1:], strict=False):
        elapsed = (later - earlier).total_seconds()
        if elapsed > threshold:
            result["gaps"].append(
                {
                    "started_at": earlier.isoformat(),
                    "ended_at": later.isoformat(),
                    "duration_seconds": round(elapsed, 2),
                }
            )
    result["status"] = "interrupted" if result["gaps"] else "continuous"
    if result["collector_error_cycles"]:
        result["status"] = "impaired" if not result["gaps"] else "interrupted"
    return result


def analyze_recording(
    metrics: list[MetricSample],
    events: list[StateEvent],
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> RecordingAnalysisResult:
    base = analyze_recording_v5(
        [sample for sample in metrics if sample.metric != CYCLE_METRIC], events
    )
    summary = dict(base.summary)
    integrity = _continuity(metrics, started_at, ended_at)
    summary["collection_integrity"] = integrity
    if integrity["status"] != "continuous":
        summary["evidence_status"] = "partial"
        if summary["status"] == "clear":
            summary["status"] = "limited"
        descriptions = {
            "unavailable": (
                "Collection continuity is unavailable: cycle markers or valid "
                "bounds/cadence are missing."
            ),
            "interrupted": (
                "Collection paused during this recording; findings do not cover the gaps."
            ),
            "impaired": (
                "Collection errors occurred during this recording; "
                "some measurements may be missing."
            ),
        }
        summary["limitations"] = [*summary["limitations"], descriptions[integrity["status"]]]

    policy = dict(base.policy)
    policy["version"] = ENGINE_VERSION
    policy["collection_continuity"] = {
        "cycle_metric": CYCLE_METRIC,
        "gap_threshold": "max(3 * configured_interval_seconds, configured_interval_seconds + 2)",
    }
    policy["notes"] = [
        *list(base.policy.get("notes", [])),
        (
            "Synchronized data confirms delivery; cycle markers describe observed "
            "collection continuity."
        ),
        "Continuous markers cannot prove that every collector produced valid measurements.",
    ]
    return RecordingAnalysisResult(summary=summary, findings=base.findings, policy=policy)
