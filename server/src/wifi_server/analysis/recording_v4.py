from dataclasses import dataclass
from datetime import datetime
from typing import Any

from wifi_server.analysis.recording import (
    RSSI_CRITICAL_DBM,
    RSSI_WARNING_DBM,
    MetricSample,
    RecordingAnalysisResult,
    StateEvent,
)
from wifi_server.analysis.recording_v2 import (
    RETRY_CRITICAL_PER_100,
    RETRY_WARNING_PER_100,
    TX_FAILURE_CRITICAL_PERCENT,
)
from wifi_server.analysis.recording_v3 import (
    CHANNEL_UTILIZATION_CRITICAL_PERCENT,
    CHANNEL_UTILIZATION_WARNING_PERCENT,
)
from wifi_server.analysis.recording_v3 import (
    analyze_recording as analyze_recording_v3,
)

ENGINE_VERSION = "recording-analysis-v4"
MIN_CORRELATED_SAMPLES = 3
MAX_CORRELATED_GAP_SECONDS = 2.5

RELEVANT_METRICS = frozenset(
    {
        "wifi.rssi_dbm",
        "wifi.tx_retries_per_100_packets",
        "wifi.tx_failed_percent",
        "wifi.channel_utilization_percent",
    }
)


@dataclass(frozen=True, slots=True)
class CorrelatedPoint:
    observed_at: datetime
    severity: str
    domains: tuple[str, ...]
    evidence: tuple[str, ...]
    values: dict[str, float]


def _classify(
    observed_at: datetime,
    values: dict[str, float],
) -> CorrelatedPoint | None:
    domains: set[str] = set()
    evidence: list[str] = []
    severity = "warning"

    rssi = values.get("wifi.rssi_dbm")
    if rssi is not None:
        if rssi < RSSI_CRITICAL_DBM:
            domains.add("signal")
            evidence.append("very_low_signal")
            severity = "critical"
        elif rssi < RSSI_WARNING_DBM:
            domains.add("signal")
            evidence.append("low_signal")

    retries = values.get("wifi.tx_retries_per_100_packets")
    if retries is not None:
        if retries >= RETRY_CRITICAL_PER_100:
            domains.add("reliability")
            evidence.append("high_retries")
            severity = "critical"
        elif retries >= RETRY_WARNING_PER_100:
            domains.add("reliability")
            evidence.append("elevated_retries")

    tx_failed = values.get("wifi.tx_failed_percent")
    if tx_failed is not None and tx_failed >= TX_FAILURE_CRITICAL_PERCENT:
        domains.add("reliability")
        evidence.append("tx_failures")
        severity = "critical"

    utilization = values.get("wifi.channel_utilization_percent")
    if utilization is not None:
        if utilization >= CHANNEL_UTILIZATION_CRITICAL_PERCENT:
            domains.add("airtime")
            evidence.append("high_channel_utilization")
            severity = "critical"
        elif utilization >= CHANNEL_UTILIZATION_WARNING_PERCENT:
            domains.add("airtime")
            evidence.append("elevated_channel_utilization")

    if len(domains) < 2:
        return None

    return CorrelatedPoint(
        observed_at=observed_at,
        severity=severity,
        domains=tuple(sorted(domains)),
        evidence=tuple(evidence),
        values=dict(values),
    )


def _metric_value(
    points: list[CorrelatedPoint],
    metric: str,
    reducer: str,
) -> float | None:
    values = [point.values[metric] for point in points if metric in point.values]
    if not values:
        return None
    value = min(values) if reducer == "min" else max(values)
    return round(value, 3)


def _window(points: list[CorrelatedPoint]) -> dict[str, Any]:
    severities = {point.severity for point in points}
    return {
        "started_at": points[0].observed_at.isoformat(),
        "ended_at": points[-1].observed_at.isoformat(),
        "duration_seconds": round(
            max(
                0.0,
                (points[-1].observed_at - points[0].observed_at).total_seconds(),
            ),
            2,
        ),
        "sample_count": len(points),
        "severity": "critical" if "critical" in severities else "warning",
        "domains": sorted({domain for point in points for domain in point.domains}),
        "evidence": sorted({evidence for point in points for evidence in point.evidence}),
        "minimum_rssi_dbm": _metric_value(points, "wifi.rssi_dbm", "min"),
        "maximum_retries_per_100_packets": _metric_value(
            points,
            "wifi.tx_retries_per_100_packets",
            "max",
        ),
        "maximum_tx_failed_percent": _metric_value(
            points,
            "wifi.tx_failed_percent",
            "max",
        ),
        "maximum_channel_utilization_percent": _metric_value(
            points,
            "wifi.channel_utilization_percent",
            "max",
        ),
    }


def _temporal_windows(
    metrics: list[MetricSample],
) -> tuple[list[dict[str, Any]], int, int]:
    by_time: dict[datetime, dict[str, float]] = {}
    for sample in metrics:
        if sample.metric not in RELEVANT_METRICS:
            continue
        values = by_time.setdefault(sample.observed_at, {})
        values[sample.metric] = sample.value

    evaluable_samples = 0
    correlated_samples = 0
    windows: list[dict[str, Any]] = []
    current: list[CorrelatedPoint] = []

    def flush() -> None:
        nonlocal current
        if len(current) >= MIN_CORRELATED_SAMPLES:
            windows.append(_window(current))
        current = []

    for observed_at, raw_values in sorted(by_time.items()):
        available_domains = {
            domain
            for domain, available in (
                ("signal", "wifi.rssi_dbm" in raw_values),
                (
                    "reliability",
                    "wifi.tx_retries_per_100_packets" in raw_values
                    or "wifi.tx_failed_percent" in raw_values,
                ),
                (
                    "airtime",
                    "wifi.channel_utilization_percent" in raw_values,
                ),
            )
            if available
        }
        if len(available_domains) >= 2:
            evaluable_samples += 1

        classified = _classify(observed_at, dict(raw_values))
        if classified is None:
            flush()
            continue

        correlated_samples += 1
        if current:
            gap = (classified.observed_at - current[-1].observed_at).total_seconds()
            if gap > MAX_CORRELATED_GAP_SECONDS:
                flush()
        current.append(classified)

    flush()
    return windows, evaluable_samples, correlated_samples


def _correlation_finding(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not windows:
        return None
    severity = (
        "critical" if any(window["severity"] == "critical" for window in windows) else "warning"
    )
    longest = max(windows, key=lambda window: float(window["duration_seconds"]))
    return {
        "code": "WIFI_CORRELATED_DEGRADATION",
        "severity": severity,
        "title": "Correlated Wi-Fi degradation observed",
        "message": (
            f"{len(windows)} sustained window(s) contained simultaneous degradation "
            "across at least two Wi-Fi evidence domains."
        ),
        "next_action": (
            "Inspect the window timestamps against AP/controller RF telemetry and "
            "client/application symptoms. Correlation narrows the investigation "
            "window but does not establish root cause."
        ),
        "evidence": {
            "window_count": len(windows),
            "longest_duration_seconds": longest["duration_seconds"],
            "windows": windows,
        },
    }


def analyze_recording(
    metrics: list[MetricSample],
    events: list[StateEvent],
) -> RecordingAnalysisResult:
    base = analyze_recording_v3(metrics, events)
    summary = dict(base.summary)
    findings = [dict(finding) for finding in base.findings]
    limitations = list(summary.get("limitations", []))
    evidence_groups = dict(summary.get("evidence_groups", {}))

    windows, evaluable_samples, correlated_samples = _temporal_windows(metrics)
    correlation_finding = _correlation_finding(windows)
    if correlation_finding is not None:
        findings.append(correlation_finding)

    summary["degraded_windows"] = windows
    summary["temporal_correlation"] = {
        "evaluable_samples": evaluable_samples,
        "correlated_samples": correlated_samples,
        "window_count": len(windows),
    }
    evidence_groups["temporal_correlation"] = evaluable_samples >= MIN_CORRELATED_SAMPLES
    summary["evidence_groups"] = evidence_groups
    summary["evidence_status"] = "complete" if all(evidence_groups.values()) else "partial"

    if evaluable_samples < MIN_CORRELATED_SAMPLES:
        limitations.append(
            f"Only {evaluable_samples} sample(s) contained at least two comparable "
            "Wi-Fi evidence domains; temporal correlation requires at least "
            f"{MIN_CORRELATED_SAMPLES}."
        )
    summary["limitations"] = limitations

    severities = {finding["severity"] for finding in findings}
    if "critical" in severities:
        summary["status"] = "critical"
    elif "warning" in severities:
        summary["status"] = "warning"
    elif findings:
        summary["status"] = "observed"
    elif metrics:
        summary["status"] = "clear"
    else:
        summary["status"] = "limited"
    summary["finding_counts"] = {
        "critical": sum(item["severity"] == "critical" for item in findings),
        "warning": sum(item["severity"] == "warning" for item in findings),
        "info": sum(item["severity"] == "info" for item in findings),
    }

    policy = dict(base.policy)
    policy.update(
        {
            "version": ENGINE_VERSION,
            "minimum_correlated_samples": MIN_CORRELATED_SAMPLES,
            "max_correlated_gap_seconds": MAX_CORRELATED_GAP_SECONDS,
            "correlation_domains": ["signal", "reliability", "airtime"],
        }
    )
    policy["notes"] = [
        *list(base.policy.get("notes", [])),
        (
            "A degraded window requires simultaneous threshold crossings in at "
            "least two evidence domains for consecutive samples."
        ),
        (
            "Temporal correlation identifies when evidence coexisted; it does not "
            "by itself establish RF root cause."
        ),
    ]
    return RecordingAnalysisResult(
        summary=summary,
        findings=findings,
        policy=policy,
    )
