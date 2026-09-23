import { useEffect, useState } from "react";
import Plot from "react-plotly.js";
import type { Config, Data, Layout } from "plotly.js";

import { getIncidentHistory } from "./api";
import {
  buildTimelineSeries,
  historicalOverview,
} from "./historyTimelineModel";
import type { TimelineMetricDefinition } from "./historyTimelineModel";
import { buildTimelineEvents, buildWifiIncidentEvents, escapeHover } from "./historyEventsModel";
import type { TimelineEvent } from "./historyEventsModel";
import type { HistoryWindow, IncidentRecord } from "./types";

import "./HistoricalTimeline.css";

type HistoryView = TimelineMetricDefinition["row"];

const VIEWS: Array<{ id: HistoryView; label: string; description: string; unit: string }> = [
  { id: "wifi", label: "Wi-Fi signal", description: "Signal strength at the connected client", unit: "RSSI (dBm)" },
  { id: "latency", label: "Response times", description: "Gateway, Internet, DNS and HTTPS response", unit: "Latency (ms)" },
  { id: "loss", label: "Packet loss", description: "Gateway and external ICMP loss", unit: "Loss (%)" },
  { id: "retries", label: "TX retries", description: "Client retransmissions per 100 TX packets", unit: "Retries / 100 TX" },
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


export default function HistoricalTimeline({ data }: { data: HistoryWindow }) {
  const [showEnvironmentChanges, setShowEnvironmentChanges] = useState(false);
  const [showWifiIncidents, setShowWifiIncidents] = useState(false);
  const [incidents, setIncidents] = useState<IncidentRecord[]>([]);
  const [incidentError, setIncidentError] = useState<string | null>(null);
  const [view, setView] = useState<HistoryView>("wifi");
  const [savedRange, setSavedRange] = useState<SavedRange | null>(null);
  const [resetRevision, setResetRevision] = useState(0);

  useEffect(() => {
    if (!showWifiIncidents) return;
    const controller = new AbortController();
    getIncidentHistory(1000, controller.signal)
      .then((records) => {
        if (!controller.signal.aborted) {
          setIncidents(records);
          setIncidentError(records.length === 1000
            ? "Incident history reached its 1,000 record limit; older Wi-Fi incidents may be missing."
            : null);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setIncidents([]);
          setIncidentError("Wi-Fi incidents could not be loaded.");
        }
      });
    return () => controller.abort();
  }, [showWifiIncidents, data.end]);

  const series = buildTimelineSeries(data, view);
  const overview = historicalOverview(data);
  const events = buildTimelineEvents(data, [], []);
  const environmentEvents = showEnvironmentChanges
    ? events.filter((event) => event.kind === "roam" || event.kind === "environment") : [];
  const wifiIncidents = showWifiIncidents ? buildWifiIncidentEvents(data, incidents) : [];
  const rangeDurationMs = Math.max(1, Date.parse(data.end) - Date.parse(data.start));
  const viewDefinition = VIEWS.find((item) => item.id === view)!;
  const hasMatchingRange = savedRange?.interfaceName === data.interface &&
    savedRange.durationMs === rangeDurationMs &&
    Date.parse(savedRange.start) < Date.parse(data.end) &&
    Date.parse(savedRange.end) > Date.parse(data.start);
  const displayRange: [string, string] = hasMatchingRange
    ? [savedRange.start, savedRange.end] : [data.start, data.end];

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

  const metricTraces: Data[] = series.map((item) => ({
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

  const metricValues = series.flatMap((item) => item.y.filter((value): value is number =>
    value !== null && Number.isFinite(value)));
  const markerY = metricValues.length ? metricValues.reduce((highest, value) =>
    Math.max(highest, value), -Infinity) : 0;
  const incidentTraces: Data[] = wifiIncidents.length ? [{
    type: "scatter", mode: "markers", showlegend: false,
    x: wifiIncidents.map((event) => event.start),
    y: wifiIncidents.map(() => markerY),
    text: wifiIncidents.map(tooltip),
    marker: { color: "#b42318", size: 12, symbol: "x" },
    hovertemplate: "%{text}<extra></extra>",
    cliponaxis: false,
  }] : [];

  const eventShapes: NonNullable<Layout["shapes"]> = [
    ...environmentEvents.map((event) => ({
      type: "line" as const,
      xref: "x" as const,
      yref: "paper" as const,
      x0: event.start,
      x1: event.start,
      y0: 0,
      y1: 1,
      line: {
        color: event.kind === "roam" ? "#00857a" : "#667085",
        width: 1,
        dash: "dot" as const,
      },
    })),
    ...wifiIncidents.filter((event) => event.end !== null).map((event) => ({
      type: "rect" as const,
      xref: "x" as const,
      yref: "paper" as const,
      x0: event.start,
      x1: event.end!,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(180, 35, 24, 0.10)",
      line: { width: 0 },
      layer: "below" as const,
    })),
  ];

  const layout: Partial<Layout> = {
    autosize: true,
    height: 430,
    margin: {
      l: 75,
      r: 24,
      t: 65,
      b: 65,
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#ffffff",
    hovermode: "x unified",
    dragmode: "zoom",
    showlegend: metricTraces.length > 1,
    legend: {
      orientation: "h",
      x: 0,
      y: 1.1,
      xanchor: "left",
      yanchor: "bottom",
    },
    uirevision: `${data.interface}-${view}-${resetRevision}-${data.end}`,
    shapes: eventShapes,
    xaxis: {
      type: "date",
      range: displayRange,
      showgrid: false,
      zeroline: false,
      rangeslider: { visible: false },
    },
    yaxis: {
      title: data.total_samples === 0 ? undefined : { text: viewDefinition.unit },
      gridcolor: "#eaecf0",
      zeroline: false,
      rangemode: view === "loss" || view === "retries" ? "tozero" : undefined,
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
          Choose a metric and the event types to compare on the same timeline. Your time zoom
          is kept when you switch metrics.
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
          className={view === item.id ? "history-view-active" : ""}
          disabled={data.total_samples === 0}
          aria-pressed={view === item.id}
          onClick={() => setView(item.id)}>{item.label}
        </button>)}
      </div>

      <div className="history-view-heading">
        <div>
          <h4>{data.total_samples === 0 ? "Recorded events" : viewDefinition.label}</h4>
          <p>{data.total_samples === 0
            ? "No measurements in this period. Select event types to inspect their timeline."
            : viewDefinition.description}</p>
        </div>
        <button type="button" onClick={() => {
          setSavedRange(null);
          setResetRevision((value) => value + 1);
        }}>Reset zoom</button>
      </div>

      <div className="history-overlay-controls" role="group" aria-label="History chart overlays">
        <label><input type="checkbox" checked={showEnvironmentChanges}
          onChange={(event) => setShowEnvironmentChanges(event.target.checked)} />
          Mark Wi-Fi environment changes on this graph</label>
        <label><input type="checkbox" checked={showWifiIncidents}
          onChange={(event) => {
            setIncidents([]);
            setIncidentError(null);
            setShowWifiIncidents(event.target.checked);
          }} />
          Show Wifi Incidents</label>
      </div>

      {incidentError && showWifiIncidents && <p className="history-incident-notice" role="status">{incidentError}</p>}

      <div className="history-plot-wrapper">
        <Plot
          key={`${view}-${resetRevision}`}
          data={[...metricTraces, ...incidentTraces]}
          layout={layout}
          config={config}
          onRelayout={(update: Record<string, unknown>) => {
            const range = relayoutRange(update);
            if (range === undefined) return;
            setSavedRange(range === null ? null : {
              start: range[0], end: range[1], interfaceName: data.interface, durationMs: rangeDurationMs,
            });
          }}
          style={{ width: "100%", height: "430px" }}
          useResizeHandler
        />
      </div>

      <p className="metric-note">
        Lines show bucket averages; hover retains min/max and P50/P95/P99. Missing readings remain gaps.
        DNS/HTTPS use the host route. Wi-Fi incident markers and shaded intervals are sensor-wide records
        and cannot be attributed to this interface alone. Environment markers show BSSID and other
        Wi-Fi changes for this interface. Incident intervals are clipped to the selected period.
      </p>

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
