from statistics import fmean
from typing import Any

from wifi_server.analysis.recording import (
    MetricSample,
    RecordingAnalysisResult,
    StateEvent,
)
from wifi_server.analysis.recording_v2 import (
    RETRY_WARNING_PER_100,
)
from wifi_server.analysis.recording_v2 import (
    analyze_recording as analyze_recording_v2,
)

ENGINE_VERSION = "recording-analysis-v3"
MIN_SURVEY_INTERVALS = 5
CHANNEL_UTILIZATION_WARNING_PERCENT = 70.0
CHANNEL_UTILIZATION_CRITICAL_PERCENT = 85.0


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


def _utilization_findings(
    utilization_stats: dict[str, float | int] | None,
    retry_stats: dict[str, float | int] | None,
) -> list[dict[str, Any]]:
    if utilization_stats is None or int(utilization_stats["samples"]) < MIN_SURVEY_INTERVALS:
        return []

    findings: list[dict[str, Any]] = []
    utilization_p90 = float(utilization_stats["p90"])
    if utilization_p90 >= CHANNEL_UTILIZATION_CRITICAL_PERCENT:
        findings.append(
            _finding(
                "WIFI_HIGH_CHANNEL_UTILIZATION",
                "critical",
                "Very high channel utilization",
                (
                    f"Channel utilization P90 reached {utilization_p90:g}% "
                    "across comparable survey intervals."
                ),
                (
                    "Inspect AP radio utilization, client load and neighboring BSS activity. "
                    "High utilization alone does not identify the traffic source."
                ),
                {"p90_percent": utilization_p90, **utilization_stats},
            )
        )
    elif utilization_p90 >= CHANNEL_UTILIZATION_WARNING_PERCENT:
        findings.append(
            _finding(
                "WIFI_ELEVATED_CHANNEL_UTILIZATION",
                "warning",
                "Elevated channel utilization",
                (
                    f"Channel utilization P90 reached {utilization_p90:g}% "
                    "across comparable survey intervals."
                ),
                (
                    "Compare utilization with AP-side radio load and retry behavior "
                    "before changing channel or channel width."
                ),
                {"p90_percent": utilization_p90, **utilization_stats},
            )
        )

    if (
        retry_stats is not None
        and float(retry_stats["p90"]) >= RETRY_WARNING_PER_100
        and utilization_p90 >= CHANNEL_UTILIZATION_WARNING_PERCENT
    ):
        findings.append(
            _finding(
                "WIFI_RETRIES_WITH_BUSY_CHANNEL",
                "info",
                "Retries coincide with a busy channel",
                (
                    f"Retry P90 was {float(retry_stats['p90']):g}/100 packets while "
                    f"channel-utilization P90 was {utilization_p90:g}%."
                ),
                (
                    "Use AP/controller RF data to distinguish expected airtime demand, "
                    "co-channel contention and non-Wi-Fi interference."
                ),
                {
                    "retry_p90_per_100_packets": float(retry_stats["p90"]),
                    "channel_utilization_p90_percent": utilization_p90,
                },
            )
        )
    return findings


def analyze_recording(
    metrics: list[MetricSample],
    events: list[StateEvent],
) -> RecordingAnalysisResult:
    base = analyze_recording_v2(metrics, events)
    summary = dict(base.summary)
    findings = [dict(finding) for finding in base.findings]
    limitations = list(summary.get("limitations", []))
    evidence_groups = dict(summary.get("evidence_groups", {}))

    by_metric: dict[str, list[MetricSample]] = {}
    for sample in metrics:
        by_metric.setdefault(sample.metric, []).append(sample)

    utilization_samples = by_metric.get("wifi.channel_utilization_percent", [])
    channel_rx_samples = by_metric.get("wifi.channel_rx_percent", [])
    channel_tx_samples = by_metric.get("wifi.channel_tx_percent", [])
    utilization_stats = _stats(utilization_samples)
    channel_rx_stats = _stats(channel_rx_samples)
    channel_tx_stats = _stats(channel_tx_samples)
    survey_intervals = max(
        len(utilization_samples),
        len(channel_rx_samples),
        len(channel_tx_samples),
    )

    retry_stats = summary.get("tx_retries_per_100_packets")
    retry_stats_dict = retry_stats if isinstance(retry_stats, dict) else None
    findings.extend(_utilization_findings(utilization_stats, retry_stats_dict))

    summary["channel_utilization_percent"] = utilization_stats
    summary["channel_rx_percent"] = channel_rx_stats
    summary["channel_tx_percent"] = channel_tx_stats
    summary["survey_intervals"] = survey_intervals
    evidence_groups["rf_utilization"] = bool(utilization_samples)
    summary["evidence_groups"] = evidence_groups
    summary["evidence_status"] = "complete" if all(evidence_groups.values()) else "partial"

    if not utilization_samples:
        limitations.append(
            "No comparable survey intervals were captured; channel utilization "
            "is unavailable on this recording."
        )
    elif survey_intervals < MIN_SURVEY_INTERVALS:
        limitations.append(
            f"Only {survey_intervals} comparable survey interval(s) were captured; "
            f"at least {MIN_SURVEY_INTERVALS} are required for utilization findings."
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
            "minimum_survey_intervals": MIN_SURVEY_INTERVALS,
            "channel_utilization_warning_percent": (CHANNEL_UTILIZATION_WARNING_PERCENT),
            "channel_utilization_critical_percent": (CHANNEL_UTILIZATION_CRITICAL_PERCENT),
        }
    )
    policy["notes"] = [
        *list(base.policy.get("notes", [])),
        (
            "Channel-utilization thresholds are project heuristics applied to P90 "
            "of same-channel survey deltas, not a universal WLAN standard."
        ),
        (
            "High utilization represents occupied airtime and does not by itself "
            "prove interference or identify the traffic source."
        ),
    ]
    return RecordingAnalysisResult(
        summary=summary,
        findings=findings,
        policy=policy,
    )
