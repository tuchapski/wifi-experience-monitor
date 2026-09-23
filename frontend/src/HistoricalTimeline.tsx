import { useState } from "react";
import Plot from "react-plotly.js";
import type { Config, Data, Layout } from "plotly.js";

import {
  buildTimelineSeries,
  historicalOverview,
} from "./historyTimelineModel";
import { buildTimelineEvents, escapeHover, EVENT_LANES } from "./historyEventsModel";
import type { EventKind, TimelineEvent } from "./historyEventsModel";
import type { ExperienceEpisode, HistoryWindow, IncidentRecord } from "./types";

import "./HistoricalTimeline.css";

type HistoryView = "wifi" | "latency" | "loss" | "retries" | "events";

const VIEWS: Array<{ id: HistoryView; label: string; description: string; unit: string }> = [
  { id: "wifi", label: "Wi-Fi signal", description: "Signal strength at the connected client", unit: "RSSI (dBm)" },
  { id: "latency", label: "Response times", description: "Gateway, Internet, DNS and HTTPS response", unit: "Latency (ms)" },
  { id: "loss", label: "Packet loss", description: "Gateway and external ICMP loss", unit: "Loss (%)" },
  { id: "retries", label: "TX retries", description: "Client retransmissions per 100 TX packets", unit: "Retries / 100 TX" },
  { id: "events", label: "Events", description: "Changes, cycles, incidents and outages", unit: "" },
];

interface SavedRange { start: string; end: string; interfaceName: string; durationMs: number }

function relayoutRange(update: Record<string, unknown>): [string, string] | null | undefined {
  if (update["xaxis.autorange"] === true) return null;
  const fullRange = update["xaxis.range"];
  const first = Array.isArray(fullRange) ? fullRange[0] : update["xaxis.range[0]"];
  const last = Array.isArray(fullRange) ? fullRange[1] : update["xaxis.range[1]"];
  if (typeof first !== "string" || typeof last !== "string" ||
    !Number.isFinite(Date.parse(first)) || !Number.isFinite(Date.parse(last)) ||
    Date.parse(first) >= Date.parse(last)) return undefined;
  return [first, last];
}


function date(value: string): string {
  return new Date(value).toLocaleString();
}


function duration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}


export default function HistoricalTimeline({
  data,
  incidents,
  episodes,
  eventNotice,
}: {
  data: HistoryWindow;
  incidents: IncidentRecord[];
  episodes: ExperienceEpisode[];
  eventNotice: string | null;
}) {
  const [hiddenEvents, setHiddenEvents] = useState<EventKind[]>([]);
  const [view, setView] = useState<HistoryView>("wifi");
  const [showChangeMarkers, setShowChangeMarkers] = useState(false);
  const [savedRange, setSavedRange] = useState<SavedRange | null>(null);
  const [resetRevision, setResetRevision] = useState(0);
  const series = buildTimelineSeries(data);
  const overview = historicalOverview(data);
  const events = buildTimelineEvents(data, incidents, episodes);
  const visibleEvents = events.filter((event) => !hiddenEvents.includes(event.kind));
  const rangeDurationMs = Math.max(1, Date.parse(data.end) - Date.parse(data.start));
  const activeView: HistoryView = data.total_samples === 0 ? "events" : view;
  const viewDefinition = VIEWS.find((item) => item.id === activeView)!;
  const hasMatchingRange = savedRange?.interfaceName === data.interface &&
    savedRange.durationMs === rangeDurationMs &&
    Date.parse(savedRange.start) < Date.parse(data.end) &&
    Date.parse(savedRange.end) > Date.parse(data.start);
  const displayRange: [string, string] = hasMatchingRange
    ? [savedRange.start, savedRange.end] : [data.start, data.end];

  function toggleEvent(kind: EventKind) {
    setHiddenEvents((hidden) => hidden.includes(kind)
      ? hidden.filter((item) => item !== kind) : [...hidden, kind]);
  }

  function tooltip(event: TimelineEvent): string {
    return [
      `<b>${escapeHover(event.label)}</b>`,
      escapeHover(event.detail),
      `Recorded: ${date(event.recordedStart)}${event.recordedEnd ? ` → ${date(event.recordedEnd)}` : ""}`,
      Date.parse(event.start) !== Date.parse(event.recordedStart) ||
        (event.end !== null && Date.parse(event.end) !== Date.parse(event.recordedEnd ?? ""))
        ? `Visible: ${date(event.start)}${event.end ? ` → ${date(event.end)}` : ""}` : "",
      event.scope === "sensor" ? "Sensor-wide record"
        : event.scope === "window" ? "Selected history window · service probe may use host route"
          : `Interface window · ${escapeHover(data.interface)}`,
    ].filter(Boolean).join("<br>");
  }

  const metricTraces: Data[] = series.filter((item) => item.row === activeView).map((item) => ({
    type: "scatter",
    mode: "lines",
    name: item.label,
    legendgroup: item.row,
    x: item.x,
    y: item.y,
    connectgaps: false,
    line: {
      color: item.color,
      width: 2,
    },
    text: item.hoverText,
    hovertemplate: "%{text}<extra></extra>",
  }));

  const eventTraces: Data[] = activeView === "events" ? EVENT_LANES.flatMap((lane) => {
    const items = visibleEvents.filter((event) => event.kind === lane.kind);
    const spans = items.filter((event) => event.end !== null);
    const points = items.filter((event) => event.end === null);
    const traces: Data[] = [];
    if (spans.length) traces.push({
      type: "scatter", mode: "lines+markers", showlegend: false,
      x: spans.flatMap((event) => [event.start, event.end!, null]),
      y: spans.flatMap(() => [lane.lane, lane.lane, null]),
      text: spans.flatMap((event) => [tooltip(event), tooltip(event), ""]),
      connectgaps: false,
      line: { color: lane.color, width: 8 },
      marker: { color: lane.color, size: 7, symbol: lane.symbol },
      hovertemplate: "%{text}<extra></extra>",
    });
    if (points.length) traces.push({
      type: "scatter", mode: "markers", showlegend: false,
      x: points.map((event) => event.start),
      y: points.map(() => lane.lane),
      text: points.map(tooltip),
      marker: { color: lane.color, size: 11, symbol: lane.symbol },
      hovertemplate: "%{text}<extra></extra>",
    });
    return traces;
  }) : [];

  const eventShapes: NonNullable<Layout["shapes"]> = activeView !== "events" && showChangeMarkers ? visibleEvents
    .filter((event) => event.kind === "environment" || event.kind === "roam")
    .map((event) => ({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: event.start,
      x1: event.start,
      y0: 0,
      y1: 1,
      line: {
        color: EVENT_LANES.find((lane) => lane.kind === event.kind)!.color,
        width: 1,
        dash: "dot",
      },
    })) : [];

  const layout: Partial<Layout> = {
    autosize: true,
    height: activeView === "events" ? 470 : 430,
    margin: {
      l: activeView === "events" ? 140 : 75,
      r: 24,
      t: activeView === "events" ? 30 : 65,
      b: 65,
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#ffffff",
    hovermode: activeView === "events" ? "closest" : "x unified",
    dragmode: "zoom",
    showlegend: activeView !== "events" && metricTraces.length > 1,
    legend: {
      orientation: "h",
      x: 0,
      y: 1.1,
      xanchor: "left",
      yanchor: "bottom",
    },
    uirevision: `${data.interface}-${activeView}-${resetRevision}-${data.end}`,
    shapes: eventShapes,
    xaxis: {
      type: "date",
      range: displayRange,
      showgrid: false,
      zeroline: false,
      rangeslider: { visible: false },
    },
    yaxis: {
      title: activeView === "events" ? undefined : { text: viewDefinition.unit },
      range: activeView === "events" ? [-0.5, 5.5] : undefined,
      tickvals: activeView === "events" ? EVENT_LANES.map((lane) => lane.lane) : undefined,
      ticktext: activeView === "events" ? EVENT_LANES.map((lane) => lane.label) : undefined,
      gridcolor: "#eaecf0",
      zeroline: false,
      fixedrange: activeView === "events",
      rangemode: activeView === "loss" || activeView === "retries" ? "tozero" : undefined,
    },
  };

  const config: Partial<Config> = {
    responsive: true,
    displaylogo: false,
    scrollZoom: true,
  };

  return (
    <section className="history-timeline" aria-labelledby="history-timeline-title">
      <div className="history-timeline-heading">
        <div>
          <span>Historical explorer</span>
          <h3 id="history-timeline-title">Measurements and events</h3>
        </div>
        <p>
          Choose one view to inspect it clearly. Each view uses the selected period and keeps
          your time zoom when you switch views.
        </p>
      </div>

      <div className="history-overview-grid">
        <article>
          <span>Stored samples</span>
          <strong>{overview.totalSamples.toLocaleString()}</strong>
        </article>
        <article>
          <span>Bucket</span>
          <strong>{duration(overview.bucketSeconds)}</strong>
        </article>
        <article>
          <span>Environment changes</span>
          <strong>{overview.environmentEvents}</strong>
        </article>
        <article>
          <span>Connection cycles</span>
          <strong>{overview.connectionCycles}</strong>
        </article>
        <article>
          <span>Observed app outages</span>
          <strong>{overview.applicationOutages}</strong>
        </article>
      </div>

      <div className="history-view-nav" role="group" aria-label="History chart view">
        {VIEWS.map((item) => <button key={item.id} type="button"
          className={activeView === item.id ? "history-view-active" : ""}
          disabled={data.total_samples === 0 && item.id !== "events"}
          aria-pressed={activeView === item.id}
          onClick={() => setView(item.id)}>{item.label}
          {item.id === "events" && <small>{events.length}</small>}
        </button>)}
      </div>

      <div className="history-view-heading">
        <div><h4>{viewDefinition.label}</h4><p>{viewDefinition.description}</p></div>
        <button type="button" onClick={() => {
          setSavedRange(null);
          setResetRevision((value) => value + 1);
        }}>Reset zoom</button>
      </div>

      {activeView === "events" ? <>
        <div className="history-event-filters" role="group" aria-label="Historical event filters">
          {EVENT_LANES.map((lane) => <label key={lane.kind}>
            <input type="checkbox" checked={!hiddenEvents.includes(lane.kind)}
              onChange={() => toggleEvent(lane.kind)} />
            <span className="history-event-swatch" style={{ backgroundColor: lane.color }} />
            {lane.label} <small>({events.filter((event) => event.kind === lane.kind).length})</small>
          </label>)}
        </div>
        {eventNotice && <p className="history-event-notice" role="status">{eventNotice}</p>}
      </> : <label className="history-marker-toggle">
        <input type="checkbox" checked={showChangeMarkers}
          onChange={(event) => setShowChangeMarkers(event.target.checked)} />
        Mark Wi-Fi environment changes on this graph
      </label>}

      <div className="history-plot-wrapper">
        <Plot
          key={`${activeView}-${resetRevision}`}
          data={[...metricTraces, ...eventTraces]}
          layout={layout}
          config={config}
          onRelayout={(update: Record<string, unknown>) => {
            const range = relayoutRange(update);
            if (range === undefined) return;
            setSavedRange(range === null ? null : {
              start: range[0], end: range[1], interfaceName: data.interface, durationMs: rangeDurationMs,
            });
          }}
          style={{ width: "100%", height: activeView === "events" ? "470px" : "430px" }}
          useResizeHandler
        />
      </div>

      {activeView === "events" ? <p className="metric-note">
        Incident and episode records are sensor-wide and cannot be attributed to this interface alone.
        Connection cycles come from the selected interface. Application outages belong to its history
        window, but service probes may use the host route. Bars are clipped to the selected period.
      </p> : <p className="metric-note">
        Lines show bucket averages; hover retains min/max and P50/P95/P99. Missing readings remain gaps.
        DNS/HTTPS use the host route. Enable change markers to compare Wi-Fi changes with these readings.
      </p>}

      {data.events.length > 0 && (
        <details className="history-event-disclosure">
          <summary>Environment changes ({data.events.length})</summary>
          <div className="history-event-list">
            {data.events.map((event, index) => (
              <article key={`${event.code}-${event.timestamp}-${index}`}>
                <time>{event.timestamp ? date(event.timestamp) : "Unknown time"}</time>
                <strong>{event.field}</strong>
                <span>{event.message}</span>
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
