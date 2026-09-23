# The report template intentionally keeps CSS/HTML in one generated document.
# ruff: noqa: E501

from html import escape
from typing import Any


def _value(value: Any) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _metric_value(point: dict[str, Any], metric: str) -> float | None:
    value = point.get("metrics", {}).get(metric, {}).get("avg")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _chart(title: str, unit: str, points: list[dict[str, Any]], metric: str) -> str:
    values = [value for point in points if (value := _metric_value(point, metric)) is not None]
    if not values:
        return (
            f"<article class='chart'><h3>{escape(title)}</h3><p>No available values.</p></article>"
        )

    low, high = min(values), max(values)
    if low == high:
        low -= 1
        high += 1

    def x(index: int) -> float:
        return 48 + index * 704 / max(1, len(points) - 1)

    def y(value: float) -> float:
        return 154 - (value - low) * 112 / (high - low)

    segments: list[list[str]] = []
    current: list[str] = []
    for index, point in enumerate(points):
        value = _metric_value(point, metric)
        if value is None:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(f"{x(index):.1f},{y(value):.1f}")
    if current:
        segments.append(current)
    lines = "".join(f'<polyline points="{escape(" ".join(segment))}" />' for segment in segments)
    labels = "".join(
        f'<text x="42" y="{y(value) + 4:.1f}" text-anchor="end">{escape(_value(value))}</text>'
        for value in (low, (low + high) / 2, high)
    )
    return f"""
    <article class="chart">
      <h3>{escape(title)}</h3>
      <svg viewBox="0 0 800 190" role="img" aria-label="{escape(title)} in {escape(unit)}">
        <line x1="48" x2="752" y1="42" y2="42" class="grid" />
        <line x1="48" x2="752" y1="98" y2="98" class="grid" />
        <line x1="48" x2="752" y1="154" y2="154" class="grid" />
        {labels}<text x="48" y="18">{escape(unit)}</text>{lines}
      </svg>
      <p class="muted">Averages of available readings; empty buckets are gaps.</p>
    </article>
    """


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _duration(value: Any) -> str:
    seconds = _numeric(value)
    if seconds is None:
        return "Unavailable"
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


def _summary_stat(summary: Any, metric: str, stat: str) -> float | None:
    if not isinstance(summary, dict):
        return None
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        return None
    values = metrics.get(metric)
    if not isinstance(values, dict):
        return None
    return _numeric(values.get(stat))


def _delta(current: float | None, previous: float | None, unit: str) -> str:
    if current is None or previous is None:
        return "Unavailable"
    difference = current - previous
    sign = "+" if difference > 0 else ""
    return f"{sign}{difference:.2f} {unit}".strip()


def _comparison_rows(window: dict[str, Any]) -> str:
    comparison = window.get("comparison")
    if not isinstance(comparison, dict):
        return '<tr><td colspan="4">Previous equivalent period was not requested.</td></tr>'
    current = comparison.get("current")
    previous = comparison.get("previous")
    definitions = (
        ("Wi-Fi signal · P50", "signal_dbm", "p50", "dBm"),
        ("Gateway latency · P95", "gateway_latency_avg_ms", "p95", "ms"),
        ("Internet latency · P95", "internet_latency_avg_ms", "p95", "ms"),
        ("DNS latency · P95", "dns_latency_ms", "p95", "ms"),
        ("HTTPS response · P95", "https_total_time_ms", "p95", "ms"),
        ("Gateway packet loss · P95", "gateway_packet_loss_percent", "p95", "%"),
        ("Internet packet loss · P95", "internet_packet_loss_percent", "p95", "%"),
        ("TX retries · P95", "tx_retries_per_100_packets", "p95", "retries/100 TX"),
    )
    rows = []
    for label, metric, stat, unit in definitions:
        current_value = _summary_stat(current, metric, stat)
        previous_value = _summary_stat(previous, metric, stat)
        rows.append(
            f"<tr><td>{escape(label)}</td>"
            f"<td>{escape(_value(current_value))} {escape(unit)}</td>"
            f"<td>{escape(_value(previous_value))} {escape(unit)}</td>"
            f"<td>{escape(_delta(current_value, previous_value, unit))}</td></tr>"
        )

    cycle_comparison = comparison.get("connection_cycles")
    if isinstance(cycle_comparison, dict):
        current_cycle = cycle_comparison.get("current")
        previous_cycle = cycle_comparison.get("previous")
        current_total = (
            current_cycle.get("total_time_ms", {}) if isinstance(current_cycle, dict) else {}
        )
        previous_total = (
            previous_cycle.get("total_time_ms", {}) if isinstance(previous_cycle, dict) else {}
        )
        current_p95 = (
            _numeric(current_total.get("p95")) if isinstance(current_total, dict) else None
        )
        previous_p95 = (
            _numeric(previous_total.get("p95")) if isinstance(previous_total, dict) else None
        )
        rows.append(
            "<tr><td>Connection ready · P95</td>"
            f"<td>{escape(_value(current_p95))} ms</td>"
            f"<td>{escape(_value(previous_p95))} ms</td>"
            f"<td>{escape(_delta(current_p95, previous_p95, 'ms'))}</td></tr>"
        )
    return "".join(rows)


def _service_comparison_rows(window: dict[str, Any]) -> str:
    comparison = window.get("comparison")
    if not isinstance(comparison, dict):
        return '<tr><td colspan="4">Previous equivalent period was not requested.</td></tr>'
    service_comparison = comparison.get("service_slo")
    if not isinstance(service_comparison, dict):
        return '<tr><td colspan="4">No comparable synthetic-service observations.</td></tr>'
    current = service_comparison.get("current")
    previous = service_comparison.get("previous")
    current = current if isinstance(current, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    names = sorted(set(current) | set(previous))
    rows = []
    for name in names:
        current_values = current.get(name, {})
        previous_values = previous.get(name, {})
        current_availability = (
            _numeric(current_values.get("availability_percent"))
            if isinstance(current_values, dict)
            else None
        )
        previous_availability = (
            _numeric(previous_values.get("availability_percent"))
            if isinstance(previous_values, dict)
            else None
        )
        rows.append(
            f"<tr><td>{escape(str(name).upper())}</td>"
            f"<td>{escape(_value(current_availability))}%</td>"
            f"<td>{escape(_value(previous_availability))}%</td>"
            f"<td>{escape(_delta(current_availability, previous_availability, '%'))}</td></tr>"
        )
    return (
        "".join(rows)
        or '<tr><td colspan="4">No comparable synthetic-service observations.</td></tr>'
    )


def _episode_rows(episodes: list[dict[str, Any]]) -> str:
    if not episodes:
        return '<tr><td colspan="8">No experience episodes overlap this period.</td></tr>'
    return "".join(
        f"<tr><td>{escape(str(item.get('severity', '')))}</td>"
        f"<td>{escape(str(item.get('status', '')))}</td>"
        f"<td>{escape(str(item.get('started_at', '')))}</td>"
        f"<td>{escape(str(item.get('ended_at') or 'Ongoing'))}</td>"
        f"<td>{escape(_duration(item.get('duration_seconds')))}</td>"
        f"<td>{escape(str(item.get('incident_count', 0)))}</td>"
        f"<td>{escape(str(item.get('primary_domain') or item.get('correlation_status', 'unavailable')))}</td>"
        f"<td>{escape(', '.join(str(code) for code in item.get('codes', [])))}</td></tr>"
        for item in episodes
    )


def _executive_observations(
    incidents: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    service_summary: dict[str, Any],
    window: dict[str, Any],
) -> str:
    critical = sum(item.get("severity") == "critical" for item in incidents)
    warning = sum(item.get("severity") == "warning" for item in incidents)
    observations = [
        f"The selected period contains {len(incidents)} incident interval(s): "
        f"{critical} critical and {warning} warning."
        if incidents
        else "No incident interval overlaps the selected period."
    ]

    correlated_domains = [
        str(item.get("primary_domain"))
        for item in episodes
        if item.get("correlation_status") == "correlated" and item.get("primary_domain")
    ]
    if episodes:
        observations.append(
            f"{len(episodes)} experience episode(s) overlap the period; "
            f"{len(correlated_domains)} have a single correlated primary domain."
        )
        if correlated_domains:
            counts = {
                domain: correlated_domains.count(domain) for domain in set(correlated_domains)
            }
            highest = max(counts.values())
            leaders = sorted(domain for domain, count in counts.items() if count == highest)
            if len(leaders) == 1:
                observations.append(
                    f"Most frequent correlated episode domain: {leaders[0]} ({highest} episode(s))."
                )
            else:
                observations.append(
                    "Correlated episodes do not have a single most-frequent domain in this period."
                )

    available_services = []
    for name, values in service_summary.items():
        if not isinstance(values, dict):
            continue
        availability = _numeric(values.get("availability_percent"))
        if availability is not None:
            available_services.append((availability, str(name)))
    if available_services:
        availability, name = min(available_services)
        observations.append(
            f"Lowest measured synthetic-service availability in the selected period: "
            f"{name.upper()} {availability:.2f}%."
        )

    comparison = window.get("comparison")
    if isinstance(comparison, dict):
        if comparison.get("reference_type") == "custom":
            observations.append(
                "Comparison values below use the selected reference period; durations and sample "
                "counts may differ. Deltas are descriptive and are not an automatic verdict."
            )
        else:
            observations.append(
                "Period-over-period values below compare this window with the immediately preceding "
                "window of equal duration; deltas are descriptive and are not an automatic verdict."
            )
    return "".join(f"<li>{escape(item)}</li>" for item in observations)


def render_html_report(
    window: dict[str, Any],
    incidents: list[dict[str, Any]],
    episodes: list[dict[str, Any]] | None = None,
) -> str:
    episodes = episodes or []
    points = window.get("points", [])
    events = window.get("events", [])
    connection_cycles = window.get("connection_cycles", [])
    connection_summary = window.get("connection_cycle_summary", {})
    service_summary = window.get("service_slo_summary", {})
    service_summary = service_summary if isinstance(service_summary, dict) else {}
    interface = escape(str(window.get("interface", "Unknown")))
    start = escape(str(window.get("start", "Unknown")))
    end = escape(str(window.get("end", "Unknown")))
    charts = "".join(
        (
            _chart("Wi-Fi signal", "dBm", points, "signal_dbm"),
            _chart("Internet latency", "ms", points, "internet_latency_avg_ms"),
            _chart("Gateway packet loss", "%", points, "gateway_packet_loss_percent"),
            _chart(
                "Wi-Fi retransmissions",
                "retries / 100 TX packets",
                points,
                "tx_retries_per_100_packets",
            ),
        )
    )
    event_rows = (
        "".join(
            f"<tr><td>{escape(str(event.get('timestamp', 'Unknown')))}</td>"
            f"<td>{escape(str(event.get('field', 'Unknown')))}</td>"
            f"<td>{escape(str(event.get('message', '')))}</td></tr>"
            for event in events
        )
        or '<tr><td colspan="3">No environment changes recorded.</td></tr>'
    )
    incident_rows = (
        "".join(
            f"<tr><td>{escape(str(item.get('severity', '')))}</td>"
            f"<td>{escape(str(item.get('domain', '')))}</td>"
            f"<td>{escape(str(item.get('code', '')))}</td>"
            f"<td>{escape(str(item.get('started_at', '')))}</td>"
            f"<td>{escape(str(item.get('ended_at') or 'Ongoing'))}</td>"
            f"<td>{escape(_duration(item.get('duration_seconds')))}</td></tr>"
            for item in incidents
        )
        or '<tr><td colspan="6">No incidents recorded.</td></tr>'
    )
    connection_rows = (
        "".join(
            f"<tr><td>{escape(str(item.get('session_type', '')))}</td>"
            f"<td>{escape(str(item.get('state', '')))}</td>"
            f"<td>{escape(str(item.get('ssid') or 'Unavailable'))}</td>"
            f"<td>{escape(str(item.get('bssid') or 'Unavailable'))}</td>"
            f"<td>{escape(str(item.get('started_at') or 'Not observed'))}</td>"
            f"<td>{escape(_value(item.get('total_time_ms')))} ms</td></tr>"
            for item in connection_cycles
        )
        or '<tr><td colspan="6">No connection cycles observed in this period.</td></tr>'
    )
    total_time = connection_summary.get("total_time_ms", {})
    stage_summaries = connection_summary.get("stages", {})
    type_rows = (
        "".join(
            f"<tr><td>{escape(str(name))}</td><td>{escape(str(count))}</td></tr>"
            for name, count in connection_summary.get("by_type", {}).items()
        )
        or '<tr><td colspan="2">No connection-cycle types observed.</td></tr>'
    )
    stage_rows = (
        "".join(
            f"<tr><td>{escape(str(name))}</td>"
            f"<td>{escape(_value(values.get('count')))}</td>"
            f"<td>{escape(_value(values.get('p50')))} ms</td>"
            f"<td>{escape(_value(values.get('p95')))} ms</td>"
            f"<td>{escape(_value(values.get('p99')))} ms</td></tr>"
            for name, values in stage_summaries.items()
        )
        or '<tr><td colspan="5">No measured connection stages.</td></tr>'
    )
    cycle_summary_cards = (
        f'<div class="card">Connection cycles<strong>{escape(_value(connection_summary.get("total_cycles")))}</strong></div>'
        f'<div class="card">Measured cycle durations<strong>{escape(_value(connection_summary.get("measurable_cycles")))}</strong></div>'
        f'<div class="card">Ready time · P50<strong>{escape(_value(total_time.get("p50")))} ms</strong></div>'
        f'<div class="card">Ready time · P95<strong>{escape(_value(total_time.get("p95")))} ms</strong></div>'
    )
    service_rows = (
        "".join(
            f"<tr><td>{escape(str(name).upper())}</td>"
            f"<td>{escape(_value(values.get('availability_percent')))}%</td>"
            f"<td>{escape(_value(values.get('success_count')))} / "
            f"{escape(_value(values.get('failure_count')))} / "
            f"{escape(_value(values.get('measurement_error_count')))}</td>"
            f"<td>{escape(_value(values.get('latency_ms', {}).get('p95')))} ms</td>"
            f"<td>{escape(_value(values.get('latency_ms', {}).get('p99')))} ms</td>"
            f"<td>{escape(_value(values.get('packet_loss_percent', {}).get('p95')))}%</td></tr>"
            for name, values in service_summary.items()
            if isinstance(values, dict) and values.get("attempt_count", 0)
        )
        or '<tr><td colspan="6">No fresh synthetic-service executions in this period.</td></tr>'
    )
    samples = sum(point.get("sample_count", 0) for point in points)
    critical_incidents = sum(item.get("severity") == "critical" for item in incidents)
    correlated_episodes = sum(item.get("correlation_status") == "correlated" for item in episodes)
    observations = _executive_observations(incidents, episodes, service_summary, window)
    comparison = window.get("comparison")
    previous_period = "Unavailable"
    custom_reference = isinstance(comparison, dict) and comparison.get("reference_type") == "custom"
    reference_label = (
        "Chosen reference period" if custom_reference else "Previous equivalent period"
    )
    column_label = "Reference" if custom_reference else "Previous"
    sample_counts = ""
    if custom_reference:
        comparison_description = (
            "Current values are compared with the chosen reference period. Durations and sample "
            "counts may differ; delta = current − reference and is descriptive, not an automatic verdict."
        )
        current_summary = comparison.get("current") if isinstance(comparison, dict) else None
        reference_summary = comparison.get("previous") if isinstance(comparison, dict) else None
        selected_count = (
            current_summary.get("sample_count", "Unknown")
            if isinstance(current_summary, dict)
            else "Unknown"
        )
        reference_count = (
            reference_summary.get("sample_count", "Unknown")
            if isinstance(reference_summary, dict)
            else "Unknown"
        )
        sample_counts = (
            f" Selected samples: {escape(str(selected_count))}; "
            f"reference samples: {escape(str(reference_count))}."
        )
    else:
        comparison_description = (
            "Current values are compared with the immediately preceding equivalent period. "
            "Delta = current − previous; positive or negative values are descriptive and are not "
            "automatically classified as better or worse."
        )
    if isinstance(comparison, dict):
        previous_period = f"{comparison.get('previous_start', 'Unknown')} – {comparison.get('previous_end', 'Unknown')}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Wi-Fi Experience Executive Report · {interface}</title><style>
body{{font-family:system-ui,sans-serif;color:#101828;background:#f2f4f7;margin:0}}
main{{max-width:1180px;margin:auto;padding:32px}}header,section,article{{background:#fff;border-radius:12px;padding:20px;margin-bottom:20px;box-shadow:0 1px 4px #0001}}
h1{{margin:0 0 8px}}h2,h3{{margin-top:0}}.muted{{color:#667085;font-size:13px;line-height:1.5}}.summary,.charts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.executive{{grid-template-columns:repeat(4,minmax(0,1fr))}}.card{{padding:12px;background:#f9fafb;border:1px solid #e4e7ec;border-radius:8px}}.card strong{{display:block;font-size:24px;margin-top:6px}}
.badge{{display:inline-block;padding:4px 8px;border-radius:999px;background:#eff4ff;color:#175cd3;font-size:12px;font-weight:700;margin-bottom:10px}}.observations{{line-height:1.6;padding-left:20px}}
.chart{{margin:0}}svg{{width:100%}}svg text{{font-size:12px;fill:#475467}}.grid{{stroke:#e4e7ec}}polyline{{fill:none;stroke:#175cd3;stroke-width:2}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #e4e7ec;vertical-align:top}}th{{color:#667085}}
@media(max-width:900px){{main{{padding:16px}}.summary,.charts,.executive{{grid-template-columns:1fr}}}}@media print{{body{{background:#fff}}main{{padding:0}}header,section,article{{box-shadow:none;border:1px solid #e4e7ec;break-inside:avoid}}}}
</style></head><body><main>
<header><span class="badge">Report v2</span><h1>Wi-Fi Experience Executive Report</h1><p class="muted">Interface: <strong>{interface}</strong><br>Selected period: {start} – {end}<br>{reference_label}: {escape(previous_period)}</p></header>
<section><h2>Executive overview</h2><div class="summary executive"><div class="card">Stored samples<strong>{samples}</strong></div><div class="card">Experience episodes<strong>{len(episodes)}</strong></div><div class="card">Incident intervals<strong>{len(incidents)}</strong></div><div class="card">Critical incidents<strong>{critical_incidents}</strong></div></div><h3>Key observations</h3><ul class="observations">{observations}</ul><p class="muted">Correlated episodes with one primary domain: {correlated_episodes}. Executive observations are derived from stored measurements, incidents and deterministic correlation evidence; they are not proof of physical root cause.</p></section>
<section><h2>Experience episodes</h2><table><thead><tr><th>Severity</th><th>Status</th><th>Started</th><th>Ended</th><th>Duration</th><th>Incidents</th><th>Correlation</th><th>Codes</th></tr></thead><tbody>{_episode_rows(episodes)}</tbody></table><p class="muted">Episodes group incident intervals separated by no more than the configured episode merge gap. Correlation is assigned only from stored correlated snapshots inside each episode.</p></section>
<section><h2>{"Selected vs reference comparison" if custom_reference else "Period-over-period comparison"}</h2><p class="muted">{escape(comparison_description)}{sample_counts}</p><table><thead><tr><th>Metric</th><th>Current</th><th>{column_label}</th><th>Delta</th></tr></thead><tbody>{_comparison_rows(window)}</tbody></table><h3>Synthetic-service availability</h3><table><thead><tr><th>Service</th><th>Current</th><th>{column_label}</th><th>Delta</th></tr></thead><tbody>{_service_comparison_rows(window)}</tbody></table></section>
<section><h2>Synthetic service SLA/SLO observations</h2><table><thead><tr><th>Service</th><th>Availability</th><th>Success / Failure / Error</th><th>Latency P95</th><th>Latency P99</th><th>Packet-loss P95</th></tr></thead><tbody>{service_rows}</tbody></table><p class="muted">Availability uses only fresh definitive passed/failed executions. Collection errors are reported separately and excluded from the denominator. These are selected-period observations; rolling compliance is evaluated against the profile-pinned runtime SLO policy.</p></section>
<section><h2>Connection cycle statistics</h2><div class="summary">{cycle_summary_cards}</div><h3>Cycles by type</h3><table><thead><tr><th>Type</th><th>Count</th></tr></thead><tbody>{type_rows}</tbody></table><h3>Stage timing percentiles</h3><table><thead><tr><th>Stage</th><th>Samples</th><th>P50</th><th>P95</th><th>P99</th></tr></thead><tbody>{stage_rows}</tbody></table><p class="muted">Percentiles exclude unknown durations rather than treating them as zero.</p></section>
<section><h2>Measurements</h2><div class="charts">{charts}</div></section>
<section><h2>Environment changes</h2><table><thead><tr><th>Time</th><th>Field</th><th>Evidence</th></tr></thead><tbody>{event_rows}</tbody></table></section>
<section><h2>Connection cycles</h2><table><thead><tr><th>Type</th><th>State</th><th>SSID</th><th>BSSID</th><th>Started</th><th>Network ready estimate</th></tr></thead><tbody>{connection_rows}</tbody></table></section>
<section><h2>Incident detail</h2><table><thead><tr><th>Severity</th><th>Domain</th><th>Code</th><th>Started</th><th>Ended</th><th>Duration</th></tr></thead><tbody>{incident_rows}</tbody></table></section>
<section><h2>Interpretation and limitations</h2><ul><li>PHY rates are radio rates, not application throughput.</li><li>DNS and HTTPS use the host route and are not proof that those tests used the selected Wi-Fi interface.</li><li>Empty buckets and unavailable values remain missing data.</li><li>Synthetic-service availability excludes sensor collection errors; a measurement error is not silently converted into a service outage.</li><li>An AP or channel change is evidence of an environment change, not by itself proof of a fault.</li><li>Connection-cycle percentiles use only observed durations. Sampling-derived values remain upper-bound estimates, while NetworkManager D-Bus stages retain their event source.</li><li>Incident and episode records are currently scoped to the sensor database rather than keyed by interface; interpret those sections carefully if the same database contains monitoring history for multiple interfaces.</li><li>Period-over-period deltas are descriptive. Threshold/SLO findings and deterministic correlation remain the sources of diagnostic interpretation.</li></ul></section>
</main></body></html>"""
