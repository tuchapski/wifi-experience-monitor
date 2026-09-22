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


def render_html_report(window: dict[str, Any], incidents: list[dict[str, Any]]) -> str:
    points = window.get("points", [])
    events = window.get("events", [])
    connection_cycles = window.get("connection_cycles", [])
    connection_summary = window.get("connection_cycle_summary", {})
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
            f"<td>{escape(str(item.get('ended_at', 'Ongoing')))}</td>"
            f"<td>{escape(str(item.get('duration_seconds', '')))} s</td></tr>"
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
    samples = sum(point.get("sample_count", 0) for point in points)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Wi-Fi Experience Report · {interface}</title><style>
body{{font-family:system-ui,sans-serif;color:#101828;background:#f2f4f7;margin:0}}
main{{max-width:1100px;margin:auto;padding:32px}}header,section,article{{background:#fff;border-radius:12px;padding:20px;margin-bottom:20px;box-shadow:0 1px 4px #0001}}
h1{{margin:0 0 8px}}h2,h3{{margin-top:0}}.muted{{color:#667085;font-size:13px}}.summary,.charts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.card{{padding:12px;background:#f9fafb;border:1px solid #e4e7ec;border-radius:8px}}.card strong{{display:block;font-size:24px;margin-top:6px}}
.chart{{margin:0}}svg{{width:100%}}svg text{{font-size:12px;fill:#475467}}.grid{{stroke:#e4e7ec}}polyline{{fill:none;stroke:#175cd3;stroke-width:2}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #e4e7ec;vertical-align:top}}
th{{color:#667085}}@media(max-width:800px){{main{{padding:16px}}.summary,.charts{{grid-template-columns:1fr}}}}@media print{{body{{background:#fff}}main{{padding:0}}header,section,article{{box-shadow:none;border:1px solid #e4e7ec;break-inside:avoid}}}}
</style></head><body><main>
<header><h1>Wi-Fi Experience Monitor report</h1><p class="muted">Interface: <strong>{interface}</strong><br>Period: {start} – {end}</p></header>
<section><h2>Summary</h2><div class="summary"><div class="card">Stored samples<strong>{samples}</strong></div><div class="card">History buckets<strong>{len(points)}</strong></div><div class="card">Environment changes<strong>{len(events)}</strong></div><div class="card">Incidents<strong>{len(incidents)}</strong></div></div></section>
<section><h2>Connection cycle statistics</h2><div class="summary">{cycle_summary_cards}</div><h3>Cycles by type</h3><table><thead><tr><th>Type</th><th>Count</th></tr></thead><tbody>{type_rows}</tbody></table><h3>Stage timing percentiles</h3><table><thead><tr><th>Stage</th><th>Samples</th><th>P50</th><th>P95</th><th>P99</th></tr></thead><tbody>{stage_rows}</tbody></table><p class="muted">Percentiles exclude unknown durations rather than treating them as zero.</p></section>
<section><h2>Measurements</h2><div class="charts">{charts}</div></section>
<section><h2>Environment changes</h2><table><thead><tr><th>Time</th><th>Field</th><th>Evidence</th></tr></thead><tbody>{event_rows}</tbody></table></section>
<section><h2>Connection cycles</h2><table><thead><tr><th>Type</th><th>State</th><th>SSID</th><th>BSSID</th><th>Started</th><th>Network ready estimate</th></tr></thead><tbody>{connection_rows}</tbody></table></section>
<section><h2>Incidents</h2><table><thead><tr><th>Severity</th><th>Domain</th><th>Code</th><th>Started</th><th>Ended</th><th>Duration (s)</th></tr></thead><tbody>{incident_rows}</tbody></table></section>
<section><h2>Interpretation and limitations</h2><ul><li>PHY rates are radio rates, not application throughput.</li><li>DNS and HTTPS use the host route and are not proof that those tests used the selected Wi-Fi interface.</li><li>Empty buckets and unavailable values remain missing data.</li><li>An AP or channel change is evidence of an environment change, not by itself proof of a fault.</li><li>Connection-cycle percentiles use only observed durations. Sampling-derived values remain upper-bound estimates, while NetworkManager D-Bus stages retain their event source.</li></ul></section>
</main></body></html>"""
