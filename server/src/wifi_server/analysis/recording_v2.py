from statistics import fmean
from typing import Any

from wifi_server.analysis.recording import (
    MetricSample,
    RecordingAnalysisResult,
    StateEvent,
)
from wifi_server.analysis.recording import (
    analyze_recording as analyze_recording_v1,
)

ENGINE_VERSION = "recording-analysis-v2"
MIN_COUNTER_INTERVALS = 5
RETRY_WARNING_PER_100 = 20.0
RETRY_CRITICAL_PER_100 = 50.0
TX_FAILURE_CRITICAL_PERCENT = 5.0


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
        "min": round(min(values), 3),
        "average": round(fmean(values), 3),
        "max": round(max(values), 3),
        "p10": round(_percentile(values, 0.10), 3),
        "p50": round(_percentile(values, 0.50), 3),
        "p90": round(_percentile(values, 0.90), 3),
    }


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


def _counter_findings(
    retry_stats: dict[str, float | int] | None,
    failure_stats: dict[str, float | int] | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if retry_stats is not None and int(retry_stats["samples"]) >= MIN_COUNTER_INTERVALS:
        p90 = float(retry_stats["p90"])
        if p90 >= RETRY_CRITICAL_PER_100:
            findings.append(
                _finding(
                    "WIFI_HIGH_RETRIES",
                    "critical",
                    "Very high retransmission activity",
                    (
                        f"TX retry P90 reached {p90:g} retries per 100 transmitted "
                        "packets across comparable intervals."
                    ),
                    (
                        "Correlate retries with RSSI, channel conditions, BSSID changes "
                        "and AP-side RF telemetry."
                    ),
                    {"p90_per_100_packets": p90, **retry_stats},
                )
            )
        elif p90 >= RETRY_WARNING_PER_100:
            findings.append(
                _finding(
                    "WIFI_ELEVATED_RETRIES",
                    "warning",
                    "Elevated retransmission activity",
                    (
                        f"TX retry P90 reached {p90:g} retries per 100 transmitted "
                        "packets across comparable intervals."
                    ),
                    (
                        "Compare retries with RSSI and roaming events before changing "
                        "RF configuration."
                    ),
                    {"p90_per_100_packets": p90, **retry_stats},
                )
            )

    if failure_stats is not None and int(failure_stats["samples"]) >= MIN_COUNTER_INTERVALS:
        p90 = float(failure_stats["p90"])
        if p90 >= TX_FAILURE_CRITICAL_PERCENT:
            findings.append(
                _finding(
                    "WIFI_TX_FAILURES",
                    "critical",
                    "High TX failure ratio",
                    (f"TX failure P90 reached {p90:g}% across comparable transmission intervals."),
                    (
                        "Correlate failures with retries, RSSI and AP/controller logs "
                        "around the affected intervals."
                    ),
                    {"p90_percent": p90, **failure_stats},
                )
            )
    return findings


def analyze_recording(
    metrics: list[MetricSample],
    events: list[StateEvent],
) -> RecordingAnalysisResult:
    base = analyze_recording_v1(metrics, events)
    summary = dict(base.summary)
    findings = [dict(finding) for finding in base.findings]
    limitations = list(summary.get("limitations", []))
    evidence_groups = dict(summary.get("evidence_groups", {}))

    by_metric: dict[str, list[MetricSample]] = {}
    for sample in metrics:
        by_metric.setdefault(sample.metric, []).append(sample)

    retry_samples = by_metric.get("wifi.tx_retries_per_100_packets", [])
    failure_samples = by_metric.get("wifi.tx_failed_percent", [])
    retry_stats = _stats(retry_samples)
    failure_stats = _stats(failure_samples)
    counter_intervals = max(len(retry_samples), len(failure_samples))

    findings.extend(_counter_findings(retry_stats, failure_stats))
    summary["tx_retries_per_100_packets"] = retry_stats
    summary["tx_failed_percent"] = failure_stats
    summary["counter_intervals"] = counter_intervals
    evidence_groups["counter_quality"] = bool(retry_samples or failure_samples)
    summary["evidence_groups"] = evidence_groups
    summary["evidence_status"] = "complete" if all(evidence_groups.values()) else "partial"

    if not retry_samples and not failure_samples:
        limitations.append(
            "No comparable TX counter intervals were captured; retry/failure "
            "quality is unavailable."
        )
    elif counter_intervals < MIN_COUNTER_INTERVALS:
        limitations.append(
            f"Only {counter_intervals} comparable TX counter interval(s) were captured; "
            f"at least {MIN_COUNTER_INTERVALS} are required for retry/failure findings."
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
            "minimum_counter_intervals": MIN_COUNTER_INTERVALS,
            "retry_warning_per_100_packets": RETRY_WARNING_PER_100,
            "retry_critical_per_100_packets": RETRY_CRITICAL_PER_100,
            "tx_failure_critical_percent": TX_FAILURE_CRITICAL_PERCENT,
        }
    )
    policy["notes"] = [
        *list(base.policy.get("notes", [])),
        (
            "Counter-quality findings use P90 of association-safe interval deltas; "
            "counter resets and BSSID changes are excluded."
        ),
    ]
    return RecordingAnalysisResult(
        summary=summary,
        findings=findings,
        policy=policy,
    )
