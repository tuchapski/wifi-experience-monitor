import { useEffect, useState } from "react";

import { startAgentRecording, stopRecording } from "./agentApi";
import { diagnosticsRecordingHash } from "./diagnosticRoutes";
import type { AgentSummary, DiagnosticRecording } from "./agentTypes";
import "./CollectionActivity.css";

function elapsedSeconds(recording: DiagnosticRecording, now: number): number {
  if (!recording.started_at) return 0;
  const ended = recording.ended_at ? Date.parse(recording.ended_at) : now;
  return Math.max(0, Math.floor((ended - Date.parse(recording.started_at)) / 1000));
}

function formatElapsed(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${remainder}s`;
  if (minutes > 0) return `${minutes}m ${remainder}s`;
  return `${remainder}s`;
}

export function CollectionActivityRow({
  agent,
  recording,
}: {
  agent: AgentSummary;
  recording: DiagnosticRecording;
}) {
  const [now, setNow] = useState(() => Date.now());
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (recording.status !== "recording") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [recording.status]);

  const elapsed = elapsedSeconds(recording, now);
  const maximumSeconds = recording.max_duration_minutes == null
    ? null
    : recording.max_duration_minutes * 60;
  const progress = maximumSeconds == null || maximumSeconds <= 0
    ? null
    : Math.min(100, (elapsed / maximumSeconds) * 100);

  async function handleStop(): Promise<void> {
    if (recording.status !== "recording" || stopping) return;
    setStopping(true);
    setError(null);
    try {
      await stopRecording(recording.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to stop collection");
      setStopping(false);
    }
  }

  return (
    <article className="collection-activity-row">
      <div className="collection-activity-live" aria-hidden="true"><i /></div>
      <div className="collection-activity-main">
        <div className="collection-activity-title">
          <span>Now collecting</span>
          <strong>{recording.name}</strong>
          <small>{agent.name} · {agent.hostname}</small>
        </div>
        <div className="collection-activity-progress">
          <div>
            <i style={{ width: `${progress ?? 100}%` }} />
          </div>
          <small>
            {formatElapsed(elapsed)}
            {recording.max_duration_minutes != null
              ? ` / ${recording.max_duration_minutes} min`
              : ""}
          </small>
        </div>
      </div>
      <dl className="collection-activity-stats">
        <div><dt>Status</dt><dd>{recording.status === "created" ? "Waiting" : recording.status}</dd></div>
        <div><dt>Metrics</dt><dd>{recording.metrics_count.toLocaleString()}</dd></div>
        <div><dt>Events</dt><dd>{recording.events_count.toLocaleString()}</dd></div>
      </dl>
      <div className="collection-activity-actions">
        <a href={`#agents/${encodeURIComponent(agent.id)}`}>View Agent</a>
        <button
          type="button"
          onClick={() => void handleStop()}
          disabled={recording.status !== "recording" || stopping}
        >
          {stopping || recording.status === "stopping"
            ? "Stopping…"
            : recording.status === "created"
              ? "Waiting for Agent"
              : "Stop"}
        </button>
      </div>
      {error && <small className="collection-activity-error">{error}</small>}
    </article>
  );
}

export function DatasetCollectionControls({
  agent,
  recording,
  hasActiveCollection,
}: {
  agent: AgentSummary;
  recording: DiagnosticRecording;
  hasActiveCollection: boolean;
}) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAnalyze = recording.status === "completed" && recording.sync_status === "complete";
  const canRepeat = agent.status === "online" && !hasActiveCollection && !starting;

  async function handleRepeat(): Promise<void> {
    if (!canRepeat) return;
    setStarting(true);
    setError(null);
    try {
      await startAgentRecording(agent.id, {
        name: recording.name,
        description: recording.description,
        site: recording.site,
        location: recording.location,
        profile_id: recording.profile_id ?? "wifi-deep-dive",
        max_duration_minutes: recording.max_duration_minutes ?? 60,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start collection");
      setStarting(false);
    }
  }

  return (
    <div className="dataset-collection-controls">
      <div>
        {canAnalyze && (
          <button
            type="button"
            onClick={() => {
              window.location.hash = diagnosticsRecordingHash(agent.id, recording.id);
            }}
          >
            View analysis
          </button>
        )}
        <button
          type="button"
          className="dataset-collect-again"
          disabled={!canRepeat}
          title={
            agent.status !== "online"
              ? "Agent is offline"
              : hasActiveCollection
                ? "Agent already has an active collection"
                : "Start a new collection with the same settings"
          }
          onClick={() => void handleRepeat()}
        >
          {starting ? "Starting…" : "Collect again"}
        </button>
      </div>
      {error && <small>{error}</small>}
    </div>
  );
}
