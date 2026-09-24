from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Any

ENGINE_VERSION = "recording-analysis-v1"

RSSI_WARNING_DBM = -75.0
RSSI_CRITICAL_DBM = -82.0
LOW_SIGNAL_MIN_SAMPLES = 5
MAX_SAMPLE_GAP_SECONDS = 2.5
RATE_VARIATION_MIN_SAMPLES = 10
RATE_P10_RATIO_WARNING = 0.5

POLICY = {
    "version": ENGINE_VERSION,
    "rssi_warning_dbm": RSSI_WARNING_DBM,
    "rssi_critical_dbm": RSSI_CRITICAL_DBM,
    "low_signal_min_consecutive_samples": LOW_SIGNAL_MIN_SAMPLES,
    "max_sample_gap_seconds": MAX_SAMPLE_GAP_SECONDS,
    "rate_variation_min_samples": RATE_VARIATION_MIN_SAMPLES,
    "rate_p10_ratio_warning": RATE_P10_RATIO_WARNING,
    "notes": [
        "RSSI thresholds preserve the project's existing V1 Wi-Fi thresholds.",
        "Rate variability is a versioned heuristic and is not proof of RF root cause.",
        "State changes describe observations; a BSSID change may be normal roaming.",
    ],
}


@dataclass(frozen=True, slots=True)
class MetricSample:
    observed_at: datetime
    metric: str
    value: float


@dataclass(frozen=True, slots=True)
class StateEvent:
    observed_at: datetime
    event_type: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RecordingAnalysisResult:
    summary: dict[str, Any]
    findings: list[dict[str, Any]]
    policy: dict[str, Any]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _stats(samples: list[MetricSample]) -> dict[str, float | int] | None:
    if not samples:
        return None
    values = [sample.value for sample in samples]
    return {
        "samples": len(values),
        "min": round(min(values), 2),
        "average": round(fmean(values), 2),
        "max": round(max(values), 2),
        "p10": round(_percentile(values, 0.10), 2),
        "p50": round(_percentile(values, 0.50), 2),
        "p90": round(_percentile(values, 0.90), 2),
    }


def _signal_windows(
    samples: list[MetricSample],
    threshold: float,
) -> list[dict[str, Any]]:
    ordered = sorted(samples, key=lambda sample: sample.observed_at)
    windows: list[list[MetricSample]] = []
    current: list[MetricSample] = []

    def flush() -> None:
        nonlocal current
        if len(current) >= LOW_SIGNAL_MIN_SAMPLES:
            windows.append(current)
        current = []

    for sample in ordered:
        if sample.value >= threshold:
            flush()
            continue
        if current:
            gap = (sample.observed_at - current[-1].observed_at).total_seconds()
            if gap > MAX_SAMPLE_GAP_SECONDS:
                flush()
        current.append(sample)
    flush()

    return [
        {
            "started_at": window[0].observed_at.isoformat(),
            "ended_at": window[-1].observed_at.isoformat(),
            "duration_seconds": round(
                max(
                    0.0,
                    (window[-1].observed_at - window[0].observed_at).total_seconds(),
                ),
                2,
            ),
            "sample_count": len(window),
            "minimum_dbm": round(min(sample.value for sample in window), 2),
            "average_dbm": round(fmean(sample.value for sample in window), 2),
            "threshold_dbm": threshold,
        }
        for window in windows
    ]


def _finding(
    code: str,
    severity: str,
    title: str,
    message: str,
    next_action: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "message": message,
        "next_action": next_action,
        "evidence": evidence,
    }


def _rate_variation_finding(
    metric: str,
    label: str,
    stats: dict[str, float | int] | None,
) -> dict[str, Any] | None:
    if stats is None or int(stats["samples"]) < RATE_VARIATION_MIN_SAMPLES:
        return None
    median = float(stats["p50"])
    p10 = float(stats["p10"])
    if median <= 0 or p10 >= median * RATE_P10_RATIO_WARNING:
        return None
    return _finding(
        code=f"WIFI_{metric.upper()}_VARIATION",
        severity="warning",
        title=f"{label} varied substantially",
        message=(f"The 10th percentile was {p10:g} Mbps while the median was {median:g} Mbps."),
        next_action=(
            "Correlate the rate drop with RSSI, BSSID/channel changes and retry data "
            "before attributing it to RF conditions."
        ),
        evidence={
            "metric": f"wifi.{metric}_rate_mbps",
            "p10_mbps": p10,
            "median_mbps": median,
            "ratio": round(p10 / median, 3),
            "samples": stats["samples"],
        },
    )


def analyze_recording(
    metrics: list[MetricSample],
    events: list[StateEvent],
) -> RecordingAnalysisResult:
    by_metric: dict[str, list[MetricSample]] = {}
    for sample in metrics:
        by_metric.setdefault(sample.metric, []).append(sample)

    rssi = by_metric.get("wifi.rssi_dbm", [])
    tx_rate = by_metric.get("wifi.tx_rate_mbps", [])
    rx_rate = by_metric.get("wifi.rx_rate_mbps", [])
    rssi_stats = _stats(rssi)
    tx_stats = _stats(tx_rate)
    rx_stats = _stats(rx_rate)

    warning_windows = _signal_windows(rssi, RSSI_WARNING_DBM)
    critical_windows = _signal_windows(rssi, RSSI_CRITICAL_DBM)

    changed_events = [event for event in events if event.event_type == "state.changed"]
    bssid_changes = [event for event in changed_events if event.data.get("metric") == "wifi.bssid"]
    channel_changes = [
        event for event in changed_events if event.data.get("metric") == "wifi.channel"
    ]
    disconnects = [
        event
        for event in changed_events
        if event.data.get("metric") == "wifi.connected" and event.data.get("current") is False
    ]

    findings: list[dict[str, Any]] = []
    if disconnects:
        findings.append(
            _finding(
                "WIFI_DISCONNECTED",
                "critical",
                "Wi-Fi disconnection observed",
                f"{len(disconnects)} transition(s) to disconnected state were captured.",
                "Correlate each timestamp with AP/controller logs and nearby signal conditions.",
                {
                    "count": len(disconnects),
                    "timestamps": [event.observed_at.isoformat() for event in disconnects],
                },
            )
        )

    if critical_windows:
        findings.append(
            _finding(
                "WIFI_VERY_LOW_SIGNAL",
                "critical",
                "Very low signal sustained",
                (
                    f"{len(critical_windows)} interval(s) contained at least "
                    f"{LOW_SIGNAL_MIN_SAMPLES} consecutive RSSI samples below "
                    f"{RSSI_CRITICAL_DBM:g} dBm."
                ),
                "Review coverage and client location, then correlate with retries and roaming.",
                {"windows": critical_windows},
            )
        )
    elif warning_windows:
        findings.append(
            _finding(
                "WIFI_LOW_SIGNAL",
                "warning",
                "Low signal sustained",
                (
                    f"{len(warning_windows)} interval(s) contained at least "
                    f"{LOW_SIGNAL_MIN_SAMPLES} consecutive RSSI samples below "
                    f"{RSSI_WARNING_DBM:g} dBm."
                ),
                "Compare nearby AP coverage and client location before changing RF settings.",
                {"windows": warning_windows},
            )
        )

    for rate_finding in (
        _rate_variation_finding("tx", "TX link rate", tx_stats),
        _rate_variation_finding("rx", "RX link rate", rx_stats),
    ):
        if rate_finding is not None:
            findings.append(rate_finding)

    if bssid_changes:
        findings.append(
            _finding(
                "WIFI_BSSID_CHANGED",
                "info",
                "Access point changed",
                f"{len(bssid_changes)} BSSID change(s) were observed during the recording.",
                "Verify whether the changes represent expected roaming and"
                "compare signal before/after.",
                {
                    "count": len(bssid_changes),
                    "timestamps": [event.observed_at.isoformat() for event in bssid_changes],
                },
            )
        )

    if channel_changes:
        findings.append(
            _finding(
                "WIFI_CHANNEL_CHANGED",
                "info",
                "Channel changed",
                f"{len(channel_changes)} channel change(s) were observed during the recording.",
                "Correlate channel changes with BSSID changes and rate/signal behavior.",
                {
                    "count": len(channel_changes),
                    "timestamps": [event.observed_at.isoformat() for event in channel_changes],
                },
            )
        )

    limitations: list[str] = []
    if not rssi:
        limitations.append("RSSI was not captured; signal quality could not be evaluated.")
    if not tx_rate and not rx_rate:
        limitations.append("Link-rate metrics were not captured; rate stability is unavailable.")
    if not events:
        limitations.append("No state events were captured; association changes are unavailable.")

    severities = {finding["severity"] for finding in findings}
    if "critical" in severities:
        diagnostic_status = "critical"
    elif "warning" in severities:
        diagnostic_status = "warning"
    elif findings:
        diagnostic_status = "observed"
    elif metrics:
        diagnostic_status = "clear"
    else:
        diagnostic_status = "limited"

    evidence_groups = {
        "signal": bool(rssi),
        "link_rate": bool(tx_rate or rx_rate),
        "state": bool(events),
    }
    evidence_status = "complete" if all(evidence_groups.values()) else "partial"

    summary = {
        "status": diagnostic_status,
        "evidence_status": evidence_status,
        "evidence_groups": evidence_groups,
        "finding_counts": {
            "critical": sum(finding["severity"] == "critical" for finding in findings),
            "warning": sum(finding["severity"] == "warning" for finding in findings),
            "info": sum(finding["severity"] == "info" for finding in findings),
        },
        "rssi": rssi_stats,
        "tx_rate_mbps": tx_stats,
        "rx_rate_mbps": rx_stats,
        "low_signal_windows": warning_windows,
        "very_low_signal_windows": critical_windows,
        "state_changes": {
            "total": len(changed_events),
            "bssid": len(bssid_changes),
            "channel": len(channel_changes),
            "disconnects": len(disconnects),
        },
        "limitations": limitations,
    }
    return RecordingAnalysisResult(
        summary=summary,
        findings=findings,
        policy=dict(POLICY),
    )
