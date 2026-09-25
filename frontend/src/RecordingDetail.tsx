import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getAgent,
  getRecording,
  getRecordingEvents,
  getRecordingMetricOverviews,
  recordingReportUrl,
} from "./agentApi";
import type {
  AnalysisDegradedWindow,
  AgentSummary,
  DiagnosticRecording,
  RecordingEvent,
  RecordingMetricOverview,
} from "./agentTypes";
import { diagnosticsAgentHash } from "./diagnosticRoutes";
import RecordingAnalysisPanel from "./RecordingAnalysisPanel";
import "./RecordingDetail.css";

const RECORDING_METRICS = [
  { key: "wifi.rssi_dbm", label: "RSSI", unit: "dBm" },
  { key: "wifi.signal_avg_dbm", label: "Signal average", unit: "dBm" },
  { key: "wifi.noise_dbm", label: "Noise", unit: "dBm" },
  { key: "wifi.snr_db", label: "SNR", unit: "dB" },
  { key: "wifi.tx_rate_mbps", label: "TX rate", unit: "Mbps" },
  { key: "wifi.rx_rate_mbps", label: "RX rate", unit: "Mbps" },
  { key: "wifi.tx_retries_per_100_packets", label: "TX retries", unit: "/100 packets" },
  { key: "wifi.tx_failed_percent", label: "TX failures", unit: "%" },
  { key: "wifi.channel_utilization_percent", label: "Channel utilization", unit: "%" },
  { key: "wifi.channel_rx_percent", label: "Channel RX airtime", unit: "%" },
  { key: "wifi.channel_tx_percent", label: "Channel TX airtime", unit: "%" },
] as const;

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);

function backToDiagnostics(agentId: string): void {
  window.location.hash = diagnosticsAgentHash(agentId);
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const endTime = end ? Date.parse(end) : Date.now();
  const seconds = Math.max(0, Math.floor((endTime - Date.parse(start)) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${remainder}s`;
  if (minutes > 0) return `${minutes}m ${remainder}s`;
  return `${remainder}s`;
}

function formatNumber(value: number | null, unit: string): string {
  if (value === null) return "—";
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return `${rendered} ${unit}`;
}

function formatClock(value: string): string {
  return new Date(value).toLocaleTimeString();
}

interface TimelineBounds {
  start: number;
  end: number;
}

function renderStateValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function RawMetricChart({
  label,
  unit,
  overview,
  timeline,
  degradedWindows,
  selectedWindow,
}: {
  label: string;
  unit: string;
  overview: RecordingMetricOverview | undefined;
  timeline: TimelineBounds | null;
  degradedWindows: AnalysisDegradedWindow[];
  selectedWindow: AnalysisDegradedWindow | null;
}) {
  const points = overview?.points ?? [];

  if (points.length === 0 || timeline === null) {
    return (
      <article className="recording-detail-chart">
        <div className="recording-detail-chart-heading">
          <div><span>{label}</span><strong>—</strong></div>
          <small>No captured samples</small>
        </div>
        <div className="recording-detail-chart-empty">Unavailable in this recording</div>
      </article>
    );
  }

  let minimum = overview?.minimum ?? Math.min(...points.map((point) => point.value));
  let maximum = overview?.maximum ?? Math.max(...points.map((point) => point.value));
  if (minimum === maximum) {
    minimum -= 1;
    maximum += 1;
  }
  const valueSpan = maximum - minimum;
  const timeSpan = Math.max(1, timeline.end - timeline.start);
  const xForTime = (time: number) => {
    const clamped = Math.min(timeline.end, Math.max(timeline.start, time));
    return 16 + ((clamped - timeline.start) / timeSpan) * 688;
  };
  const x = (point: { observed_at: string }) =>
    xForTime(Date.parse(point.observed_at));
  const y = (value: number) => 154 - ((value - minimum) / valueSpan) * 126;
  const polyline = points.map((point) => `${x(point)},${y(point.value)}`).join(" ");
  const latest = points[points.length - 1];
  const selectedKey = selectedWindow
    ? `${selectedWindow.started_at}:${selectedWindow.ended_at}`
    : null;

  return (
    <article className="recording-detail-chart">
      <div className="recording-detail-chart-heading">
        <div>
          <span>{label}</span>
          <strong>{formatNumber(latest.value, unit)}</strong>
        </div>
        <small>{(overview?.sample_count ?? 0).toLocaleString()} samples across full recording</small>
      </div>
      <svg viewBox="0 0 720 174" role="img" aria-label={`${label} recording overview chart`}>
        {degradedWindows.map((window) => {
          const startX = xForTime(Date.parse(window.started_at));
          const endX = xForTime(Date.parse(window.ended_at));
          const key = `${window.started_at}:${window.ended_at}`;
          const selected = key === selectedKey;
          return (
            <rect
              key={key}
              x={startX}
              y="28"
              width={Math.max(1.5, endX - startX)}
              height="126"
              className={[
                "recording-detail-window-band",
                `band-${window.severity}`,
                selected ? "is-selected" : "",
              ].join(" ")}
              aria-hidden="true"
            />
          );
        })}
        <line x1="16" x2="704" y1="28" y2="28" className="recording-detail-gridline" />
        <line x1="16" x2="704" y1="91" y2="91" className="recording-detail-gridline" />
        <line x1="16" x2="704" y1="154" y2="154" className="recording-detail-gridline" />
        <polyline points={polyline} className="recording-detail-line" />
      </svg>
      <div className="recording-detail-chart-axis">
        <span>{new Date(timeline.start).toLocaleTimeString()}</span>
        <span>{new Date(timeline.end).toLocaleTimeString()}</span>
      </div>
      <div className="recording-detail-chart-stats">
        <span>Min <strong>{formatNumber(overview?.minimum ?? null, unit)}</strong></span>
        <span>Avg <strong>{formatNumber(overview?.average ?? null, unit)}</strong></span>
        <span>Max <strong>{formatNumber(overview?.maximum ?? null, unit)}</strong></span>
      </div>
    </article>
  );
}

function InvestigationTimeline({
  timeline,
  degradedWindows,
  events,
  selectedWindow,
  onSelectWindow,
}: {
  timeline: TimelineBounds | null;
  degradedWindows: AnalysisDegradedWindow[];
  events: RecordingEvent[];
  selectedWindow: AnalysisDegradedWindow | null;
  onSelectWindow: (window: AnalysisDegradedWindow) => void;
}) {
  if (timeline === null) return null;

  const duration = Math.max(1, timeline.end - timeline.start);
  const positionForTime = (value: string) => {
    const time = Date.parse(value);
    if (!Number.isFinite(time)) return null;
    const clamped = Math.min(timeline.end, Math.max(timeline.start, time));
    return ((clamped - timeline.start) / duration) * 100;
  };
  const eventLane = (event: RecordingEvent) => {
    const metric = renderStateValue(event.data.metric).toLowerCase();
    if (metric.includes("bssid")) return "bssid";
    if (metric.includes("channel")) return "channel";
    return "state";
  };
  const lanes = [
    { key: "degraded", label: "Degraded windows" },
    { key: "bssid", label: "BSSID changes" },
    { key: "channel", label: "Channel changes" },
    { key: "state", label: "Other state" },
  ] as const;
  const selectedKey = selectedWindow
    ? `${selectedWindow.started_at}:${selectedWindow.ended_at}`
    : null;

  return (
    <section className="agent-panel recording-investigation">
      <div className="recording-detail-section-heading">
        <div>
          <span className="agent-eyebrow">Investigation timeline</span>
          <h2>Wi-Fi evidence on one clock</h2>
          <p>Compare degraded periods with observed state changes across the recording.</p>
        </div>
        <small>Temporal proximity is context for investigation, not proof of causality.</small>
      </div>
      <div className="recording-investigation-body">
        <div className="recording-investigation-axis" aria-hidden="true">
          <span>{new Date(timeline.start).toLocaleTimeString()}</span>
          <span>{new Date(timeline.end).toLocaleTimeString()}</span>
        </div>
        {lanes.map((lane) => (
          <div className="recording-investigation-row" key={lane.key}>
            <strong>{lane.label}</strong>
            <div className="recording-investigation-track">
              <i className="recording-investigation-baseline" aria-hidden="true" />
              {lane.key === "degraded" && degradedWindows.map((window) => {
                const start = positionForTime(window.started_at);
                const end = positionForTime(window.ended_at);
                if (start === null || end === null) return null;
                const key = `${window.started_at}:${window.ended_at}`;
                return (
                  <button
                    type="button"
                    key={key}
                    className={[
                      "recording-investigation-window",
                      `window-${window.severity}`,
                      selectedKey === key ? "is-selected" : "",
                    ].join(" ")}
                    style={{ left: `${start}%`, width: `${Math.max(0.35, end - start)}%` }}
                    title={`${window.severity}: ${formatClock(window.started_at)} → ${formatClock(window.ended_at)} · ${window.domains.join(" + ")}`}
                    aria-label={`Focus ${window.severity} degraded window from ${formatClock(window.started_at)} to ${formatClock(window.ended_at)}`}
                    onClick={() => onSelectWindow(window)}
                  />
                );
              })}
              {lane.key !== "degraded" && events.map((event, index) => {
                if (eventLane(event) !== lane.key) return null;
                const left = positionForTime(event.observed_at);
                if (left === null) return null;
                const detail = eventDescription(event);
                const description = event.event_type === "state.initial"
                  ? `${detail.metric}: ${detail.current}`
                  : `${detail.metric}: ${detail.previous} → ${detail.current}`;
                return (
                  <i
                    key={`${event.observed_at}-${event.event_type}-${index}`}
                    className={`recording-investigation-marker marker-${lane.key}`}
                    style={{ left: `${left}%` }}
                    title={`${formatClock(event.observed_at)} · ${description}`}
                    aria-label={`${formatClock(event.observed_at)} ${description}`}
                  />
                );
              })}
            </div>
          </div>
        ))}
        <div className="recording-investigation-legend">
          <span><i className="legend-window legend-warning" />Warning degradation</span>
          <span><i className="legend-window legend-critical" />Critical degradation</span>
          <span><i className="legend-marker" />Observed state change</span>
        </div>
      </div>
    </section>
  );
}

function DiagnosticEvidencePanel({
  selectedWindow,
  events,
}: {
  selectedWindow: AnalysisDegradedWindow | null;
  events: RecordingEvent[];
}) {
  if (selectedWindow === null) return null;

  const startedAt = Date.parse(selectedWindow.started_at);
  const endedAt = Date.parse(selectedWindow.ended_at);
  const contextPaddingMs = 30_000;
  const contextualEvents = events.filter((event) => {
    const observedAt = Date.parse(event.observed_at);
    return Number.isFinite(observedAt)
      && observedAt >= startedAt - contextPaddingMs
      && observedAt <= endedAt + contextPaddingMs;
  });
  const metrics = [
    { label: "Minimum RSSI", value: selectedWindow.minimum_rssi_dbm, unit: "dBm" },
    {
      label: "Maximum TX retries",
      value: selectedWindow.maximum_retries_per_100_packets,
      unit: "/100 packets",
    },
    {
      label: "Maximum TX failures",
      value: selectedWindow.maximum_tx_failed_percent,
      unit: "%",
    },
    {
      label: "Maximum channel utilization",
      value: selectedWindow.maximum_channel_utilization_percent,
      unit: "%",
    },
  ];

  return (
    <section className="agent-panel recording-evidence">
      <div className="recording-detail-section-heading">
        <div>
          <span className="agent-eyebrow">Diagnostic evidence</span>
          <h2>Evidence for the focused degraded window</h2>
          <p>
            Observations recorded for the selected interval, with nearby state changes for context.
          </p>
        </div>
        <small>Evidence is descriptive; temporal proximity alone does not establish causality.</small>
      </div>

      <div className="recording-evidence-window">
        <div>
          <span>Focused interval</span>
          <strong>{formatClock(selectedWindow.started_at)} → {formatClock(selectedWindow.ended_at)}</strong>
        </div>
        <div>
          <span>Severity</span>
          <strong className={`recording-evidence-severity severity-${selectedWindow.severity}`}>
            {selectedWindow.severity}
          </strong>
        </div>
        <div>
          <span>Duration</span>
          <strong>{selectedWindow.duration_seconds.toFixed(1)}s</strong>
        </div>
        <div>
          <span>Domains</span>
          <strong>{selectedWindow.domains.join(" + ") || "—"}</strong>
        </div>
      </div>

      <div className="recording-evidence-grid">
        <article>
          <h3>Window measurements</h3>
          <dl className="recording-evidence-metrics">
            {metrics.map((metric) => (
              <div key={metric.label}>
                <dt>{metric.label}</dt>
                <dd>{formatNumber(metric.value, metric.unit)}</dd>
              </div>
            ))}
          </dl>
        </article>

        <article>
          <h3>Analysis evidence</h3>
          {selectedWindow.evidence.length === 0 ? (
            <p className="recording-evidence-empty">No additional evidence was recorded.</p>
          ) : (
            <ul className="recording-evidence-list">
              {selectedWindow.evidence.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          )}
        </article>

        <article className="recording-evidence-events">
          <div className="recording-evidence-events-heading">
            <h3>Nearby state changes</h3>
            <small>30s before → 30s after</small>
          </div>
          {contextualEvents.length === 0 ? (
            <p className="recording-evidence-empty">No state changes were observed near this window.</p>
          ) : (
            <div className="recording-evidence-event-list">
              {contextualEvents.map((event, index) => {
                const detail = eventDescription(event);
                const observedAt = Date.parse(event.observed_at);
                const phase = observedAt < startedAt
                  ? "before"
                  : observedAt > endedAt
                    ? "after"
                    : "during";
                return (
                  <div key={`${event.observed_at}-${event.event_type}-${index}`}>
                    <time>{formatClock(event.observed_at)}</time>
                    <span className={`recording-evidence-phase phase-${phase}`}>{phase}</span>
                    <strong>{detail.metric}</strong>
                    <span>
                      {event.event_type === "state.initial"
                        ? detail.current
                        : `${detail.previous} → ${detail.current}`}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </article>
      </div>
    </section>
  );
}

function eventDescription(event: RecordingEvent): {
  metric: string;
  previous: string;
  current: string;
} {
  return {
    metric: renderStateValue(event.data.metric),
    previous: renderStateValue(event.data.previous),
    current: renderStateValue(event.data.current),
  };
}

export default function RecordingDetail({
  agentId,
  recordingId,
}: {
  agentId: string;
  recordingId: string;
}) {
  const [agent, setAgent] = useState<AgentSummary | null>(null);
  const [recording, setRecording] = useState<DiagnosticRecording | null>(null);
  const [series, setSeries] = useState<Record<string, RecordingMetricOverview>>({});
  const [events, setEvents] = useState<RecordingEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [degradedWindows, setDegradedWindows] = useState<AnalysisDegradedWindow[]>([]);
  const [selectedWindow, setSelectedWindow] =
    useState<AnalysisDegradedWindow | null>(null);

  const shouldPoll = recording === null
    || ACTIVE_STATUSES.has(recording.status)
    || recording.sync_status === "pending"
    || recording.sync_status === "syncing";

  const timeline = useMemo<TimelineBounds | null>(() => {
    const pointTimes = Object.values(series)
      .flatMap((overview) => overview.points)
      .map((point) => Date.parse(point.observed_at))
      .filter(Number.isFinite);
    const recordingStart = recording?.started_at
      ? Date.parse(recording.started_at)
      : Number.NaN;
    const recordingEnd = recording?.ended_at
      ? Date.parse(recording.ended_at)
      : Number.NaN;
    const start = Number.isFinite(recordingStart)
      ? recordingStart
      : pointTimes.length > 0
        ? Math.min(...pointTimes)
        : Number.NaN;
    const end = Number.isFinite(recordingEnd)
      ? recordingEnd
      : pointTimes.length > 0
        ? Math.max(...pointTimes)
        : Number.NaN;
    if (!Number.isFinite(start) || !Number.isFinite(end)) {
      return null;
    }
    return { start, end: end > start ? end : start + 1 };
  }, [recording?.ended_at, recording?.started_at, series]);

  const handleWindowsChange = useCallback((windows: AnalysisDegradedWindow[]) => {
    setDegradedWindows(windows);
    setSelectedWindow((current) => {
      if (current === null) return null;
      return windows.some(
        (window) =>
          window.started_at === current.started_at
          && window.ended_at === current.ended_at,
      )
        ? current
        : null;
    });
  }, []);

  const handleSelectWindow = useCallback((selected: AnalysisDegradedWindow) => {
    setSelectedWindow(selected);
    window.requestAnimationFrame(() => {
      document.getElementById("recording-raw-metrics")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, []);

  useEffect(() => {
    let active = true;

    async function refresh(): Promise<void> {
      try {
        const [agentData, recordingData, eventData] = await Promise.all([
          getAgent(agentId),
          getRecording(recordingId),
          getRecordingEvents(recordingId),
        ]);
        if (active) {
          setAgent(agentData);
          setRecording(recordingData);
          setEvents(eventData);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load recording");
          setLoading(false);
        }
      }
    }

    async function refreshSeries(): Promise<void> {
      try {
        const overviews = await getRecordingMetricOverviews(
          recordingId, RECORDING_METRICS.map(({ key }) => key),
        );
        if (active) {
          setSeries(Object.fromEntries(overviews.map((item) => [item.metric, item])));
          setSeriesError(null);
        }
      } catch (err) {
        if (active) setSeriesError(err instanceof Error ? err.message : "Unable to load charts");
      }
    }

    void refresh();
    void refreshSeries();
    if (!shouldPoll) {
      return () => {
        active = false;
      };
    }

    const timer = window.setInterval(() => void refresh(), 4000);
    const chartTimer = window.setInterval(() => void refreshSeries(), 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.clearInterval(chartTimer);
    };
  }, [agentId, recordingId, shouldPoll]);

  if (loading && !recording) {
    return <div className="agent-empty">Loading diagnostic recording…</div>;
  }

  if (!recording) {
    return (
      <div className="agent-error" role="alert">
        {error ?? "Recording not found"}
        <button type="button" onClick={() => backToDiagnostics(agentId)}>Back to diagnostics</button>
      </div>
    );
  }

  return (
    <>
      <button type="button" className="agent-back" onClick={() => {
        if (recording.project_id) window.location.hash = "#diagnostics";
        else backToDiagnostics(agentId);
      }}>
        ← {recording.project_id ? "Projects" : `Diagnostics · ${agent?.name ?? "Agent"}`}
      </button>

      <section className="recording-detail-heading">
        <div>
          <span className="agent-eyebrow">
            {recording.project_id ? "Project recording" : "Individual recording"}
          </span>
          <h1>{recording.name}</h1>
          <p>
            High-resolution observations captured by {agent?.name ?? recording.agent_id}.
          </p>
        </div>
        <div className="recording-detail-badges">
          <span className={`recording-detail-status status-${recording.status}`}>
            {recording.status}
          </span>
          <span className={`recording-detail-sync sync-${recording.sync_status}`}>
            {recording.sync_status}
          </span>
          {!ACTIVE_STATUSES.has(recording.status) && (
            <a className="recording-report-link" href={recordingReportUrl(recording.id)} download>
              Download HTML report
            </a>
          )}
        </div>
      </section>

      {(error || seriesError) && (
        <div className="agent-error" role="alert">{error || seriesError}</div>
      )}

      {(recording.project_id || recording.site || recording.location || recording.description) && (
        <section className="recording-detail-context" aria-label="Recording context">
          {recording.project_id && (
            <div>
              <span>Project</span>
              <strong>{recording.project_name ?? recording.project_id}</strong>
              <a href="#diagnostics">View project runs</a>
            </div>
          )}
          {recording.site && <div><span>Site</span><strong>{recording.site}</strong></div>}
          {recording.location && (
            <div><span>Location</span><strong>{recording.location}</strong></div>
          )}
          {recording.description && (
            <div className="recording-detail-notes">
              <span>Session notes</span>
              <p>{recording.description}</p>
            </div>
          )}
        </section>
      )}

      <section className="recording-detail-summary">
        <article><span>Started</span><strong>{formatDate(recording.started_at)}</strong></article>
        <article><span>Duration</span><strong>{formatDuration(recording.started_at, recording.ended_at)}</strong></article>
        <article><span>Raw metrics</span><strong>{recording.metrics_count.toLocaleString()}</strong></article>
        <article><span>State events</span><strong>{recording.events_count.toLocaleString()}</strong></article>
        <article><span>Profile</span><strong>{recording.profile_id ?? "—"}</strong></article>
        <article><span>Max duration</span><strong>{recording.max_duration_minutes == null ? "—" : `${recording.max_duration_minutes} min`}</strong></article>
      </section>

      {recording.sync_status !== "complete" && (
        <section className="recording-detail-notice">
          <strong>Dataset is still synchronizing</strong>
          <span>
            Charts and event counts may continue to change until sync status becomes complete.
          </span>
        </section>
      )}

      <RecordingAnalysisPanel
        recording={recording}
        selectedWindow={selectedWindow}
        onSelectWindow={handleSelectWindow}
        onWindowsChange={handleWindowsChange}
      />

      <InvestigationTimeline
        timeline={timeline}
        degradedWindows={degradedWindows}
        events={events}
        selectedWindow={selectedWindow}
        onSelectWindow={handleSelectWindow}
      />

      <DiagnosticEvidencePanel
        selectedWindow={selectedWindow}
        events={events}
      />

      <section
        id="recording-raw-metrics"
        className="agent-panel recording-detail-data"
      >
        <div className="recording-detail-section-heading">
          <div>
            <span className="agent-eyebrow">Metric overview</span>
            <h2>Wi-Fi telemetry across the full recording</h2>
            <p>Charts retain interval extremes; statistics use every captured observation.</p>
          </div>
          <small>Original measurements remain available for analysis.</small>
        </div>
        {selectedWindow && (
          <div className="recording-detail-focus">
            <div>
              <span>Focused degraded window</span>
              <strong>
                {formatClock(selectedWindow.started_at)} →{" "}
                {formatClock(selectedWindow.ended_at)}
              </strong>
              <small>
                {selectedWindow.duration_seconds.toFixed(1)}s ·{" "}
                {selectedWindow.domains.join(" + ")}
              </small>
            </div>
            <button
              type="button"
              onClick={() => setSelectedWindow(null)}
            >
              Clear focus
            </button>
          </div>
        )}
        <div className="recording-detail-chart-grid">
          {RECORDING_METRICS.map((metric) => (
            <RawMetricChart
              key={metric.key}
              label={metric.label}
              unit={metric.unit}
              overview={series[metric.key]}
              timeline={timeline}
              degradedWindows={degradedWindows}
              selectedWindow={selectedWindow}
            />
          ))}
        </div>
      </section>

      <section className="agent-panel recording-detail-events">
        <div className="recording-detail-section-heading">
          <div>
            <span className="agent-eyebrow">State timeline</span>
            <h2>Observed state changes</h2>
            <p>Initial Wi-Fi state and changes detected while the recording was active.</p>
          </div>
          <small>{events.length.toLocaleString()} events loaded</small>
        </div>

        {events.length === 0 ? (
          <div className="recording-detail-empty">No state events were captured.</div>
        ) : (
          <div className="recording-event-list">
            {events.map((event, index) => {
              const detail = eventDescription(event);
              return (
                <article
                  key={`${event.observed_at}-${event.event_type}-${index}`}
                  className="recording-event"
                >
                  <div className="recording-event-marker" aria-hidden="true"><i /></div>
                  <time>{formatDate(event.observed_at)}</time>
                  <div>
                    <div className="recording-event-title">
                      <strong>{detail.metric}</strong>
                      <span>{event.event_type === "state.initial" ? "Initial state" : "Changed"}</span>
                    </div>
                    <p>
                      {event.event_type === "state.initial"
                        ? <>Value <strong>{detail.current}</strong></>
                        : <><strong>{detail.previous}</strong> → <strong>{detail.current}</strong></>}
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="agent-panel recording-detail-metadata">
        <div className="recording-detail-section-heading">
          <div>
            <span className="agent-eyebrow">Dataset</span>
            <h2>Recording metadata</h2>
          </div>
        </div>
        <dl>
          <dt>Recording ID</dt><dd><code>{recording.id}</code></dd>
          <dt>Agent ID</dt><dd><code>{recording.agent_id}</code></dd>
          <dt>Agent version</dt><dd>{recording.agent_version ?? "—"}</dd>
          <dt>Schema version</dt><dd>{recording.schema_version}</dd>
          <dt>Created</dt><dd>{formatDate(recording.created_at)}</dd>
          <dt>Ended</dt><dd>{formatDate(recording.ended_at)}</dd>
        </dl>
      </section>
    </>
  );
}
