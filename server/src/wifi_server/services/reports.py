"""Render a standalone, evidence-aware HTML report for one diagnostic recording."""

from datetime import UTC, datetime
from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wifi_server.db.analysis_models import RecordingAnalysis
from wifi_server.recording_schemas import RecordingResponse
from wifi_server.services.recordings import get_recording


def _text(value: object) -> str:
    return escape(str(value)) if value is not None else "—"


def _date(value: datetime | None) -> str:
    return _text(value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")) if value else "—"


def _list(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "<p>No limitations recorded.</p>"
    return "<ul>" + "".join(f"<li>{_text(item)}</li>" for item in items) + "</ul>"


def _metric(summary: dict[str, Any], key: str, label: str, unit: str) -> str:
    data = summary.get(key)
    if not isinstance(data, dict):
        return f"<tr><th>{escape(label)}</th><td>—</td><td>—</td></tr>"
    average = data.get("average")
    p90 = data.get("p90")

    def cell(value: object) -> str:
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            return "—"
        return f"{value:.1f} {escape(unit)}"

    return f"<tr><th>{escape(label)}</th><td>{cell(average)}</td><td>{cell(p90)}</td></tr>"


def _findings(analysis: RecordingAnalysis) -> str:
    if not analysis.findings:
        return "<p>No heuristic findings were triggered by the available evidence.</p>"
    cards = []
    for finding in analysis.findings:
        if not isinstance(finding, dict):
            continue
        cards.append(
            "<article class='finding'>"
            f"<small>{_text(finding.get('severity'))} · {_text(finding.get('code'))}</small>"
            f"<h3>{_text(finding.get('title'))}</h3>"
            f"<p>{_text(finding.get('message'))}</p>"
            f"<strong>Suggested next action</strong><p>{_text(finding.get('next_action'))}</p>"
            "</article>"
        )
    return "".join(cards) or "<p>No readable findings were stored.</p>"


def _intervals(summary: dict[str, Any]) -> str:
    intervals = summary.get("disconnection_intervals")
    if not isinstance(intervals, list) or not intervals:
        return "<p>No disconnection interval was identified in the available evidence.</p>"
    rows = []
    for interval in intervals:
        if not isinstance(interval, dict):
            continue
        duration = interval.get("duration_seconds")
        measured = f"{duration:g} s" if isinstance(duration, (int, float)) else "—"
        limitations = interval.get("limitations")
        notes = "; ".join(map(str, limitations)) if isinstance(limitations, list) else ""
        rows.append(
            "<tr>"
            f"<td>{_text(interval.get('disconnected_at'))}</td>"
            f"<td>{_text(interval.get('reconnected_at'))}</td>"
            f"<td>{_text(interval.get('status'))}</td>"
            f"<td>{_text(measured)}</td><td>{_text(notes)}</td>"
            "</tr>"
        )
    if not rows:
        return "<p>No readable intervals were stored.</p>"
    return (
        "<div class='table-wrap'><table><thead><tr><th>Disconnected</th><th>Reconnected</th>"
        "<th>Evidence</th><th>Sampled duration</th><th>Limitations</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render_recording_report(
    recording: RecordingResponse,
    analysis: RecordingAnalysis | None,
) -> str:
    """Render recorded observations without inferring a project-wide assessment."""
    current = (
        analysis is not None
        and analysis.status == "complete"
        and recording.status == "completed"
        and recording.sync_status == "complete"
        and analysis.source_metrics_count == recording.metrics_count
        and analysis.source_events_count == recording.events_count
    )
    context = "".join(
        f"<dt>{escape(label)}</dt><dd>{_text(value)}</dd>"
        for label, value in (
            ("Agent ID", recording.agent_id),
            ("Project", recording.project_name or recording.project_id),
            ("Site", recording.site),
            ("Location", recording.location),
            ("Notes", recording.description),
            ("Started", _date(recording.started_at)),
            ("Ended", _date(recording.ended_at)),
            ("Collection status", recording.status),
            ("Sync status", recording.sync_status),
            ("Metrics received", recording.metrics_count),
            ("Events received", recording.events_count),
        )
    )
    if current and analysis is not None:
        summary = analysis.summary
        metrics = "".join(
            _metric(summary, key, label, unit)
            for key, label, unit in (
                ("rssi", "RSSI", "dBm"),
                ("tx_retries_per_100_packets", "TX retries", "/100 packets"),
                ("tx_failed_percent", "TX failures", "%"),
                ("channel_utilization_percent", "Channel utilization", "%"),
            )
        )
        integrity = summary.get("collection_integrity")
        continuity = integrity.get("status") if isinstance(integrity, dict) else "unavailable"
        assessment = (
            "<section><h2>Analysis</h2>"
            f"<p><strong>Assessment:</strong> {_text(summary.get('status'))} · "
            f"<strong>Evidence:</strong> {_text(summary.get('evidence_status'))} · "
            f"<strong>Continuity:</strong> {_text(continuity)}</p>"
            f"<p>Engine {_text(analysis.engine_version)} · "
            f"analyzed {_date(analysis.created_at)}</p>"
            "<h3>Observed metrics</h3><div class='table-wrap'><table><thead><tr>"
            "<th>Metric</th><th>Average</th><th>P90</th></tr></thead><tbody>"
            + metrics
            + "</tbody></table></div><h3>Evidence limitations</h3>"
            + _list(summary.get("limitations"))
            + "</section><section><h2>Findings</h2>"
            + _findings(analysis)
            + "</section><section><h2>Observed disconnection intervals</h2>"
            + _intervals(summary)
            + "</section>"
        )
    else:
        assessment = (
            "<section><h2>Analysis unavailable</h2>"
            "<p>This recording has no current analysis for a completed and fully "
            "synchronized dataset. Collection status and counts are shown above; "
            "no findings or conclusions are inferred.</p></section>"
        )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Diagnostic report · {_text(recording.name)}</title>"
        "<style>"
        "body{font:15px/1.55 system-ui,sans-serif;color:#20334d;background:#f4f7fb;"
        "margin:0}main{max-width:940px;margin:auto;padding:32px 24px 72px}"
        "section{background:#fff;border:1px solid #dfe6ef;border-radius:12px;"
        "padding:20px 24px;margin:20px 0;break-inside:avoid}h1{margin:4px 0}"
        "h2{margin-top:0;font-size:20px}h3{font-size:16px;margin-bottom:8px}"
        "small,.muted{color:#62738a}dl{display:grid;grid-template-columns:180px 1fr;"
        "gap:8px 18px}dt{color:#657184}dd{margin:0;overflow-wrap:anywhere}"
        "table{width:100%;border-collapse:collapse}td,th{text-align:left;vertical-align:top;"
        "border-bottom:1px solid #e5eaf1;padding:9px}th{font-weight:700}.table-wrap{overflow:auto}"
        ".finding{border-top:1px solid #e5eaf1;padding:12px 0}li{margin:6px 0}"
        "@media(max-width:620px){dl{grid-template-columns:1fr}main{padding:20px 12px}}"
        "@media print{body{background:#fff}main{padding:0}section{border-color:#bbb}}"
        "</style></head><body><main>"
        "<header><small>Wi-Fi Experience Monitor · Diagnostic recording</small>"
        f"<h1>{_text(recording.name)}</h1>"
        f"<p class='muted'>Recording {_text(recording.id)} · "
        f"generated {_date(datetime.now(UTC))}</p>"
        "</header><section><h2>Collection context</h2><dl>"
        + context
        + "</dl></section>"
        + assessment
        + "<footer class='muted'>This report describes observations from one Agent. "
        "Its findings do not establish root cause or represent a project-wide verdict.</footer>"
        "</main></body></html>"
    )


def get_recording_report(session: Session, recording_id: str) -> str:
    recording = get_recording(session, recording_id)
    analysis = session.scalar(
        select(RecordingAnalysis)
        .where(RecordingAnalysis.recording_id == recording_id)
        .order_by(RecordingAnalysis.created_at.desc(), RecordingAnalysis.id.desc())
        .limit(1)
    )
    return render_recording_report(recording, analysis)
