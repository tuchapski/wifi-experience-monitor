import Plot from "react-plotly.js";
import type { Config, Data, Layout } from "plotly.js";

import {
  buildTimelineSeries,
  historicalOverview,
} from "./historyTimelineModel";
import type { HistoryWindow } from "./types";

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
}: {
  data: HistoryWindow;
}) {
  const series = buildTimelineSeries(data);
  const overview = historicalOverview(data);
  const rangeDurationMs = Math.max(1, Date.parse(data.end) - Date.parse(data.start));

  const traces: Data[] = series.map((item) => ({
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

  const eventShapes: NonNullable<Layout["shapes"]> = data.events
    .filter((event) => event.timestamp)
    .map((event) => ({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: event.timestamp!,
      x1: event.timestamp!,
      y0: 0,
      y1: 1,
      line: {
        color: "#b42318",
        width: 1,
        dash: "dot",
      },
    }));

  const layout: Partial<Layout> = {
    autosize: true,
    height: 760,
    margin: {
      l: 72,
      r: 24,
      t: 48,
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
      domain: [0.79, 1],
      title: { text: "RSSI (dBm)" },
      gridcolor: "#eaecf0",
      zeroline: false,
    },
    yaxis2: {
      domain: [0.53, 0.74],
      title: { text: "Latency (ms)" },
      gridcolor: "#eaecf0",
      zeroline: false,
    },
    yaxis3: {
      domain: [0.29, 0.48],
      title: { text: "Loss (%)" },
      gridcolor: "#eaecf0",
      zeroline: false,
      rangemode: "tozero",
    },
    yaxis4: {
      domain: [0.07, 0.24],
      title: { text: "Retries / 100 TX" },
      gridcolor: "#eaecf0",
      zeroline: false,
      rangemode: "tozero",
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
          Hover once to inspect all visible series at the same timestamp. Zoom or pan applies
          across Wi-Fi, network and service measurements together.
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

      <div className="history-plot-wrapper">
        <Plot
          data={traces}
          layout={layout}
          config={config}
          style={{ width: "100%", minHeight: "760px" }}
          useResizeHandler
        />
      </div>

      <p className="metric-note">
        Dashed vertical markers represent stored environment changes. Lines are bucket averages;
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
