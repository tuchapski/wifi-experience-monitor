"""Describe observed Wi-Fi disconnection intervals with explicit evidence limits."""

from datetime import datetime
from typing import Any

from wifi_server.analysis.recording import MetricSample, RecordingAnalysisResult, StateEvent
from wifi_server.analysis.recording_v6 import (
    CYCLE_METRIC,
)
from wifi_server.analysis.recording_v6 import (
    analyze_recording as analyze_recording_v6,
)

ENGINE_VERSION = "recording-analysis-v7"


def _outages(
    metrics: list[MetricSample],
    events: list[StateEvent],
    integrity: dict[str, Any],
    started_at: datetime | None,
    ended_at: datetime | None,
) -> list[dict[str, Any]]:
    changes = sorted(
        (
            event
            for event in events
            if event.event_type in {"state.initial", "state.changed"}
            and event.data.get("metric") == "wifi.connected"
            and isinstance(event.data.get("current"), bool)
            and (started_at is None or event.observed_at >= started_at)
            and (ended_at is None or event.observed_at <= ended_at)
        ),
        key=lambda event: event.observed_at,
    )
    gap_bounds = [
        (datetime.fromisoformat(gap["started_at"]), datetime.fromisoformat(gap["ended_at"]))
        for gap in integrity["gaps"]
    ]
    error_cycles = [
        sample.observed_at
        for sample in metrics
        if sample.metric == CYCLE_METRIC
        and isinstance(sample.labels.get("collector_errors_count"), int)
        and sample.labels["collector_errors_count"] > 0
    ]
    outages: list[dict[str, Any]] = []
    disconnected: StateEvent | None = None
    for event in changes:
        if event.data["current"] is False:
            if disconnected is None:
                disconnected = event
            continue
        if disconnected is None:
            continue

        reasons: list[str] = []
        if (
            disconnected.event_type != "state.changed"
            or disconnected.data.get("previous") is not True
        ):
            reasons.append(
                "Disconnection start was not observed as a connected-to-disconnected change."
            )
        if event.event_type != "state.changed" or event.data.get("previous") is not False:
            reasons.append("Reconnection was not observed as a disconnected-to-connected change.")
        if integrity["status"] == "unavailable":
            reasons.append("Collection continuity could not be verified for this interval.")
        if any(
            gap_start < event.observed_at and gap_end >= disconnected.observed_at
            for gap_start, gap_end in gap_bounds
        ):
            reasons.append(
                "Collection paused around this interval; its boundaries may have been missed."
            )
        if any(
            disconnected.observed_at <= error_at <= event.observed_at for error_at in error_cycles
        ):
            reasons.append("A collection cycle reported errors within this interval.")

        outages.append(
            {
                "disconnected_at": disconnected.observed_at.isoformat(),
                "reconnected_at": event.observed_at.isoformat(),
                "status": "limited" if reasons else "bounded",
                "duration_seconds": (
                    round((event.observed_at - disconnected.observed_at).total_seconds(), 2)
                    if not reasons
                    else None
                ),
                "limitations": reasons,
            }
        )
        disconnected = None

    if disconnected is not None:
        outages.append(
            {
                "disconnected_at": disconnected.observed_at.isoformat(),
                "reconnected_at": None,
                "status": "open",
                "duration_seconds": None,
                "limitations": ["Reconnection was not observed before the recording ended."],
            }
        )
    return outages


def analyze_recording(
    metrics: list[MetricSample],
    events: list[StateEvent],
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> RecordingAnalysisResult:
    base = analyze_recording_v6(metrics, events, started_at=started_at, ended_at=ended_at)
    summary = dict(base.summary)
    outages = _outages(metrics, events, summary["collection_integrity"], started_at, ended_at)
    summary["disconnection_intervals"] = outages
    summary["disconnection_summary"] = {
        "total": len(outages),
        "bounded": sum(item["status"] == "bounded" for item in outages),
        "limited": sum(item["status"] == "limited" for item in outages),
        "open": sum(item["status"] == "open" for item in outages),
    }
    if any(item["status"] != "bounded" for item in outages):
        summary["evidence_status"] = "partial"
        if summary["status"] == "clear":
            summary["status"] = "limited"
        summary["limitations"] = [
            *summary["limitations"],
            "Some disconnection intervals lack observed boundaries or uninterrupted collection.",
        ]

    policy = dict(base.policy)
    policy["version"] = ENGINE_VERSION
    policy["notes"] = [
        *list(base.policy.get("notes", [])),
        (
            "Bounded intervals measure time between sampled transitions, "
            "not exact radio outage length."
        ),
        (
            "Intervals crossing collection gaps, lacking a known start or "
            "remaining open have no duration."
        ),
    ]
    return RecordingAnalysisResult(summary=summary, findings=base.findings, policy=policy)
