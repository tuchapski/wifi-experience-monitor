import { useEffect, useMemo, useState } from "react";

import {
  getAgent,
  getRecording,
  getRecordingEvents,
  getRecordingMetrics,
} from "./agentApi";
import type {
  AgentSummary,
  DiagnosticRecording,
  RecordingEvent,
  RecordingMetricPoint,
} from "./agentTypes";
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
] as const;

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);

function backToAgent(agentId: string): void {
  window.location.hash = `#agents/${encodeURIComponent(agentId)}`;
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

function formatNumber(value: number, unit: string): string {
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return `${rendered} ${unit}`;
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

function downsample(
  points: RecordingMetricPoint[],
  maxPoints = 500,
): RecordingMetricPoint[] {
  if (points.length <= maxPoints) return points;
  const stride = Math.ceil(points.length / maxPoints);
  return points.filter((_, index) => index % stride === 0 || index === points.length - 1);
}

function RawMetricChart({
  label,
  unit,
  points,
}: {
  label: string;
  unit: string;
  points: RecordingMetricPoint[];
}) {
  const sampled = useMemo(() => downsample(points), [points]);

  if (sampled.length === 0) {
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

  const values = sampled.map((point) => point.value);
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (minimum === maximum) {
    minimum -= 1;
    maximum += 1;
  }
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  const valueSpan = maximum - minimum;
  const firstTime = Date.parse(sampled[0].observed_at);
  const lastTime = Date.parse(sampled[sampled.length - 1].observed_at);
  const timeSpan = Math.max(1, lastTime - firstTime);
  const x = (point: RecordingMetricPoint) =>
    16 + ((Date.parse(point.observed_at) - firstTime) / timeSpan) * 688;
  const y = (value: number) => 154 - ((value - minimum) / valueSpan) * 126;
  const polyline = sampled.map((point) => `${x(point)},${y(point.value)}`).join(" ");
  const latest = sampled[sampled.length - 1];

  return (
    <article className="recording-detail-chart">
      <div className="recording-detail-chart-heading">
        <div>
          <span>{label}</span>
          <strong>{formatNumber(latest.value, unit)}</strong>
        </div>
        <small>{points.length.toLocaleString()} raw samples</small>
      </div>
      <svg viewBox="0 0 720 174" role="img" aria-label={`${label} raw recording chart`}>
        <line x1="16" x2="704" y1="28" y2="28" className="recording-detail-gridline" />
        <line x1="16" x2="704" y1="91" y2="91" className="recording-detail-gridline" />
        <line x1="16" x2="704" y1="154" y2="154" className="recording-detail-gridline" />
        <polyline points={polyline} className="recording-detail-line" />
      </svg>
      <div className="recording-detail-chart-stats">
        <span>Min <strong>{formatNumber(Math.min(...values), unit)}</strong></span>
        <span>Avg <strong>{formatNumber(average, unit)}</strong></span>
        <span>Max <strong>{formatNumber(Math.max(...values), unit)}</strong></span>
      </div>
    </article>
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
  const [series, setSeries] = useState<Record<string, RecordingMetricPoint[]>>({});
  const [events, setEvents] = useState<RecordingEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const shouldPoll = recording === null
    || ACTIVE_STATUSES.has(recording.status)
    || recording.sync_status === "pending"
    || recording.sync_status === "syncing";

  useEffect(() => {
    let active = true;

    async function refresh(): Promise<void> {
      try {
        const [agentData, recordingData, eventData, metricSeries] = await Promise.all([
          getAgent(agentId),
          getRecording(recordingId),
          getRecordingEvents(recordingId),
          Promise.all(
            RECORDING_METRICS.map(async ({ key }) => [
              key,
              await getRecordingMetrics(recordingId, key),
            ] as const),
          ),
        ]);
        if (active) {
          setAgent(agentData);
          setRecording(recordingData);
          setEvents(eventData);
          setSeries(Object.fromEntries(metricSeries));
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

    void refresh();
    if (!shouldPoll) {
      return () => {
        active = false;
      };
    }

    const timer = window.setInterval(() => void refresh(), 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [agentId, recordingId, shouldPoll]);

  if (loading && !recording) {
    return <div className="agent-empty">Loading diagnostic recording…</div>;
  }

  if (!recording) {
    return (
      <div className="agent-error" role="alert">
        {error ?? "Recording not found"}
        <button type="button" onClick={() => backToAgent(agentId)}>Back to agent</button>
      </div>
    );
  }

  return (
    <>
      <button type="button" className="agent-back" onClick={() => backToAgent(agentId)}>
        ← {agent?.name ?? "Agent"}
      </button>

      <section className="recording-detail-heading">
        <div>
          <span className="agent-eyebrow">Diagnostic recording</span>
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
        </div>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}

      <section className="recording-detail-summary">
        <article><span>Started</span><strong>{formatDate(recording.started_at)}</strong></article>
        <article><span>Duration</span><strong>{formatDuration(recording.started_at, recording.ended_at)}</strong></article>
        <article><span>Raw metrics</span><strong>{recording.metrics_count.toLocaleString()}</strong></article>
        <article><span>State events</span><strong>{recording.events_count.toLocaleString()}</strong></article>
        <article><span>Profile</span><strong>{recording.profile_id ?? "—"}</strong></article>
      </section>

      {recording.sync_status !== "complete" && (
        <section className="recording-detail-notice">
          <strong>Dataset is still synchronizing</strong>
          <span>
            Charts and event counts may continue to change until sync status becomes complete.
          </span>
        </section>
      )}

      <RecordingAnalysisPanel recording={recording} />

      <section className="agent-panel recording-detail-data">
        <div className="recording-detail-section-heading">
          <div>
            <span className="agent-eyebrow">Raw metrics</span>
            <h2>High-resolution Wi-Fi telemetry</h2>
            <p>Each point represents an observation captured by the Agent, without rolling-window aggregation.</p>
          </div>
          <small>Charts downsample only for rendering; Server data remains raw.</small>
        </div>
        <div className="recording-detail-chart-grid">
          {RECORDING_METRICS.map((metric) => (
            <RawMetricChart
              key={metric.key}
              label={metric.label}
              unit={metric.unit}
              points={series[metric.key] ?? []}
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
