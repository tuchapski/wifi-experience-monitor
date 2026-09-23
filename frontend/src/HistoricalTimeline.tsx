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
  const series = buildTimelineSeries(data);
  const overview = historicalOverview(data);
  const events = buildTimelineEvents(data, incidents, episodes);
  const visibleEvents = events.filter((event) => !hiddenEvents.includes(event.kind));
  const rangeDurationMs = Math.max(1, Date.parse(data.end) - Date.parse(data.start));

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

  const metricTraces: Data[] = series.map((item) => ({
    type: "scatter",
    mode: "lines",
    name: item.label,
    legendgroup: item.row,
    x: item.x,
    y: item.y,
    yaxis: item.axis,
    connectgaps: false,
    line: {
      color: item.color,
      width: 2,
    },
    text: item.hoverText,
    hovertemplate: "%{text}<extra></extra>",
  }));

  const eventTraces: Data[] = EVENT_LANES.flatMap((lane) => {
    const items = visibleEvents.filter((event) => event.kind === lane.kind);
    const spans = items.filter((event) => event.end !== null);
    const points = items.filter((event) => event.end === null);
    const traces: Data[] = [];
    if (spans.length) traces.push({
      type: "scatter", mode: "lines+markers", showlegend: false,
      x: spans.flatMap((event) => [event.start, event.end!, null]),
      y: spans.flatMap(() => [lane.lane, lane.lane, null]),
      text: spans.flatMap((event) => [tooltip(event), tooltip(event), ""]),
      yaxis: "y5", connectgaps: false,
      line: { color: lane.color, width: 8 },
      marker: { color: lane.color, size: 7, symbol: lane.symbol },
      hovertemplate: "%{text}<extra></extra>",
    });
    if (points.length) traces.push({
      type: "scatter", mode: "markers", showlegend: false,
      x: points.map((event) => event.start),
      y: points.map(() => lane.lane),
      text: points.map(tooltip),
      yaxis: "y5",
      marker: { color: lane.color, size: 11, symbol: lane.symbol },
      hovertemplate: "%{text}<extra></extra>",
    });
    return traces;
  });

  const eventShapes: NonNullable<Layout["shapes"]> = visibleEvents
    .filter((event) => event.kind === "environment" || event.kind === "roam")
    .map((event) => ({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: event.start,
      x1: event.start,
      y0: 0,
      y1: 0.82,
      line: {
        color: EVENT_LANES.find((lane) => lane.kind === event.kind)!.color,
        width: 1,
        dash: "dot",
      },
    }));

  const layout: Partial<Layout> = {
    autosize: true,
    height: 950,
    margin: {
      l: 135,
      r: 24,
      t: 58,
      b: 78,
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#ffffff",
    hovermode: "x unified",
    dragmode: "zoom",
    showlegend: true,
    legend: {
      orientation: "h",
      x: 0,
      y: 1.08,
      xanchor: "left",
      yanchor: "bottom",
    },
    uirevision: `${data.interface}-${rangeDurationMs}-${data.bucket_seconds}`,
    shapes: eventShapes,
    xaxis: {
      type: "date",
      anchor: "y4",
      range: [data.start, data.end],
      showgrid: false,
      zeroline: false,
      rangeslider: {
        visible: true,
        thickness: 0.07,
      },
    },
    yaxis: {
      domain: [0.65, 0.8],
      title: { text: "RSSI (dBm)" },
      gridcolor: "#eaecf0",
      zeroline: false,
    },
    yaxis2: {
      domain: [0.42, 0.62],
      title: { text: "Latency (ms)" },
      gridcolor: "#eaecf0",
      zeroline: false,
    },
    yaxis3: {
      domain: [0.23, 0.39],
      title: { text: "Loss (%)" },
      gridcolor: "#eaecf0",
      zeroline: false,
      rangemode: "tozero",
    },
    yaxis4: {
      domain: [0.05, 0.2],
      title: { text: "Retries / 100 TX" },
      gridcolor: "#eaecf0",
      zeroline: false,
      rangemode: "tozero",
    },
    yaxis5: {
      domain: [0.83, 1],
      range: [-0.5, 5.5],
      tickvals: EVENT_LANES.map((lane) => lane.lane),
      ticktext: EVENT_LANES.map((lane) => lane.label),
      gridcolor: "#eaecf0",
      zeroline: false,
      fixedrange: true,
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
          <span>Shared time axis</span>
          <h3 id="history-timeline-title">Experience timeline</h3>
        </div>
        <p>
          Events and measurements use the same time axis. Zoom and pan apply to all rows together.
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

      <div className="history-event-filters" role="group" aria-label="Historical event filters">
        {EVENT_LANES.map((lane) => <label key={lane.kind}>
          <input type="checkbox" checked={!hiddenEvents.includes(lane.kind)}
            onChange={() => toggleEvent(lane.kind)} />
          <span className="history-event-swatch" style={{ backgroundColor: lane.color }} />
          {lane.label} <small>({events.filter((event) => event.kind === lane.kind).length})</small>
        </label>)}
      </div>

      {eventNotice && <p className="history-event-notice" role="status">{eventNotice}</p>}
      <p className="metric-note">
        Incident and episode records are sensor-wide and cannot be attributed to this interface alone.
        Connection cycles come from the selected interface. Application outages are recorded in its
        history window, but service probes may use the host route. Bars are clipped to
        the selected period; a bar reaching its edge does not prove the event started or ended there.
      </p>

      <div className="history-plot-wrapper">
        <Plot
          data={[...metricTraces, ...eventTraces]}
          layout={layout}
          config={config}
          style={{ width: "100%", minHeight: "950px" }}
          useResizeHandler
        />
      </div>

      <p className="metric-note">
        Dashed vertical markers represent stored Wi-Fi environment changes. Lines are bucket averages;
        hover details retain min/max and P50/P95/P99. Missing readings remain null and Plotly does
        not connect across those gaps. DNS/HTTPS are host-routed observations.
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
