import { useLayoutEffect, useRef, useState } from "react";
import Plot from "react-plotly.js";
import type { Config, Data, Layout } from "plotly.js";

import {
  buildTimelineSeries,
  historicalOverview,
} from "./historyTimelineModel";
import type { TimelineMetricDefinition } from "./historyTimelineModel";
import { buildTimelineEvents, escapeHover, EVENT_LANES } from "./historyEventsModel";
import type { TimelineEvent } from "./historyEventsModel";
import type { HistoryWindow } from "./types";

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


const WIFI_LANES = EVENT_LANES.filter((lane) =>
  lane.kind === "connection" || lane.kind === "roam" || lane.kind === "environment");

export default function HistoricalTimeline({ data }: { data: HistoryWindow }) {
  const [showEnvironmentChanges, setShowEnvironmentChanges] = useState(false);
  const [showWifiEvents, setShowWifiEvents] = useState(false);
  const [view, setView] = useState<HistoryView>("wifi");
  const [savedRange, setSavedRange] = useState<SavedRange | null>(null);
  const [resetRevision, setResetRevision] = useState(0);
  const plotWrapper = useRef<HTMLDivElement>(null);
  const [plotWidth, setPlotWidth] = useState(0);

  useLayoutEffect(() => {
    const node = plotWrapper.current;
    if (!node) return;
    const measure = () => {
      const width = node.clientWidth;
      if (width > 0) setPlotWidth((previous) => previous === width ? previous : width);
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    window.addEventListener("resize", measure);
    const frame = requestAnimationFrame(measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      cancelAnimationFrame(frame);
    };
  }, []);

  const series = buildTimelineSeries(data, view);
  const overview = historicalOverview(data);
  const events = buildTimelineEvents(data, [], []);
  const visibleEvents = events.filter((event) =>
    (showEnvironmentChanges && (event.kind === "roam" || event.kind === "environment")) ||
    (showWifiEvents && event.kind === "connection"));
  const showEvents = visibleEvents.length > 0;
  const plotHeight = showEvents ? 560 : 430;
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

  const eventTraces: Data[] = showEvents ? WIFI_LANES.flatMap((lane) => {
    const items = visibleEvents.filter((event) => event.kind === lane.kind);
    const spans = items.filter((event) => event.end !== null);
    const points = items.filter((event) => event.end === null);
    const traces: Data[] = [];
    if (spans.length) traces.push({
      type: "scatter", mode: "lines+markers", showlegend: false, yaxis: "y2",
      x: spans.flatMap((event) => [event.start, event.end!, null]),
      y: spans.flatMap(() => [lane.lane, lane.lane, null]),
      text: spans.flatMap((event) => [tooltip(event), tooltip(event), ""]),
      connectgaps: false,
      line: { color: lane.color, width: 8 },
      marker: { color: lane.color, size: 7, symbol: lane.symbol },
      hovertemplate: "%{text}<extra></extra>",
    });
    if (points.length) traces.push({
      type: "scatter", mode: "markers", showlegend: false, yaxis: "y2",
      x: points.map((event) => event.start),
      y: points.map(() => lane.lane),
      text: points.map(tooltip),
      marker: { color: lane.color, size: 11, symbol: lane.symbol },
      hovertemplate: "%{text}<extra></extra>",
    });
    return traces;
  }) : [];

  const eventShapes: NonNullable<Layout["shapes"]> = showEvents ? visibleEvents
    .filter((event) => event.kind === "environment" || event.kind === "roam")
    .map((event) => ({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: event.start,
      x1: event.start,
      y0: 0,
      y1: data.total_samples === 0 ? 0 : 0.72,
      line: {
        color: EVENT_LANES.find((lane) => lane.kind === event.kind)!.color,
        width: 1,
        dash: "dot",
      },
    })) : [];

  const layout: Partial<Layout> = {
    autosize: false,
    width: plotWidth,
    height: plotHeight,
    margin: {
      l: showEvents ? 140 : 75,
      r: 24,
      t: 65,
      b: 65,
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#ffffff",
    hovermode: showEvents ? "closest" : "x unified",
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
      domain: showEvents ? [0, data.total_samples === 0 ? 0.01 : 0.72] : undefined,
      visible: data.total_samples > 0,
      gridcolor: "#eaecf0",
      zeroline: false,
      rangemode: view === "loss" || view === "retries" ? "tozero" : undefined,
    },
    yaxis2: showEvents ? {
      domain: data.total_samples === 0 ? [0.05, 1] : [0.78, 1],
      range: [-0.5, 2.5],
      tickvals: WIFI_LANES.map((lane) => lane.lane),
      ticktext: WIFI_LANES.map((lane) => lane.label),
      tickfont: { size: 10 },
      showgrid: false,
      zeroline: false,
      fixedrange: true,
    } : undefined,
  };

  const config: Partial<Config> = {
    responsive: false,
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
        <label><input type="checkbox" checked={showWifiEvents}
          onChange={(event) => setShowWifiEvents(event.target.checked)} />
          Show Wifi Events</label>
      </div>

      <div className="history-plot-wrapper" ref={plotWrapper}>
        {plotWidth > 0 ? <Plot
          key={`${view}-${resetRevision}`}
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
          style={{ width: `${plotWidth}px`, height: `${plotHeight}px` }}
        /> : <p role="status" className="history-chart-loading">Preparing historical chart…</p>}
      </div>

      <p className="metric-note">
        Lines show bucket averages; hover retains min/max and P50/P95/P99. Missing readings remain gaps.
        DNS/HTTPS use the host route. Wi-Fi events show connection cycles for this interface;
        environment changes show BSSID and other Wi-Fi changes. Event bars are clipped to the selected period.
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
