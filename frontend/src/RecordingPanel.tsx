import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  getAgentRecordings,
  startAgentRecording,
  stopRecording,
} from "./agentApi";
import type {
  AgentSummary,
  DiagnosticRecording,
} from "./agentTypes";
import "./RecordingPanel.css";

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);

const STATUS_LABELS: Record<string, string> = {
  created: "Waiting for agent",
  recording: "Recording",
  stopping: "Stopping",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

const SYNC_LABELS: Record<string, string> = {
  pending: "Pending",
  syncing: "Syncing",
  complete: "Synced",
  incomplete: "Incomplete",
  failed: "Failed",
};

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function formatDuration(start: string | null, end: string | null, now: number): string {
  if (!start) return "—";
  const startTime = Date.parse(start);
  const endTime = end ? Date.parse(end) : now;
  const seconds = Math.max(0, Math.floor((endTime - startTime) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${remainder}s`;
  if (minutes > 0) return `${minutes}m ${remainder}s`;
  return `${remainder}s`;
}

function statusClass(status: string): string {
  return `recording-status recording-status-${status}`;
}

function syncClass(status: string): string {
  return `recording-sync recording-sync-${status}`;
}

function navigateToRecording(agentId: string, recordingId: string): void {
  window.location.hash = `#agents/${encodeURIComponent(agentId)}/recordings/${encodeURIComponent(recordingId)}`;
}

export default function RecordingPanel({ agent }: { agent: AgentSummary }) {
  const [recordings, setRecordings] = useState<DiagnosticRecording[]>([]);
  const [recordingName, setRecordingName] = useState("");
  const [site, setSite] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [maxDurationMinutes, setMaxDurationMinutes] = useState(60);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<"start" | "stop" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const activeRecording = useMemo(
    () => recordings.find((recording) => ACTIVE_STATUSES.has(recording.status)) ?? null,
    [recordings],
  );

  async function refresh(): Promise<void> {
    try {
      const data = await getAgentRecordings(agent.id);
      setRecordings(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load diagnostic recordings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;

    async function poll(): Promise<void> {
      try {
        const data = await getAgentRecordings(agent.id);
        if (active) {
          setRecordings(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load diagnostic recordings");
          setLoading(false);
        }
      }
    }

    void poll();
    const timer = window.setInterval(() => void poll(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [agent.id]);

  useEffect(() => {
    if (!activeRecording) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeRecording]);

  async function handleStart(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (activeRecording || agent.status !== "online" || action) return;

    setAction("start");
    setError(null);
    try {
      const name = recordingName.trim()
        || `Diagnostic ${new Date().toLocaleString()}`;
      await startAgentRecording(agent.id, {
        name,
        description: notes.trim() || null,
        site: site.trim() || null,
        location: location.trim() || null,
        profile_id: "wifi-deep-dive",
        max_duration_minutes: maxDurationMinutes,
      });
      setRecordingName("");
      setSite("");
      setLocation("");
      setNotes("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start recording");
    } finally {
      setAction(null);
    }
  }

  async function handleStop(): Promise<void> {
    if (!activeRecording || activeRecording.status !== "recording" || action) return;

    setAction("stop");
    setError(null);
    try {
      await stopRecording(activeRecording.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to stop recording");
    } finally {
      setAction(null);
    }
  }

  return (
    <section className="agent-panel recording-panel">
      <div className="recording-heading">
        <div>
          <span className="agent-eyebrow">Diagnostic recording</span>
          <h2>Capture high-resolution evidence</h2>
          <p>
            Preserve raw Wi-Fi observations and state changes for deeper analysis.
          </p>
        </div>
        {!activeRecording && (
          <form className="recording-start-form" onSubmit={(event) => void handleStart(event)}>
            <div className="recording-start-fields">
              <input
                type="text"
                maxLength={255}
                value={recordingName}
                onChange={(event) => setRecordingName(event.target.value)}
                placeholder="Optional recording name"
                aria-label="Recording name"
                disabled={agent.status !== "online" || action !== null}
              />
              <select
                aria-label="Maximum recording duration"
                value={maxDurationMinutes}
                onChange={(event) => setMaxDurationMinutes(Number(event.target.value))}
                disabled={agent.status !== "online" || action !== null}
              >
                <option value={15}>15 min</option>
                <option value={30}>30 min</option>
                <option value={60}>1 hour</option>
                <option value={120}>2 hours</option>
                <option value={240}>4 hours</option>
                <option value={480}>8 hours</option>
                <option value={1440}>24 hours</option>
              </select>
              <input
                type="text"
                maxLength={255}
                value={site}
                onChange={(event) => setSite(event.target.value)}
                placeholder="Site (optional)"
                aria-label="Recording site"
                disabled={agent.status !== "online" || action !== null}
              />
              <input
                type="text"
                maxLength={255}
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="Floor / room (optional)"
                aria-label="Recording location"
                disabled={agent.status !== "online" || action !== null}
              />
            </div>
            <textarea
              maxLength={2000}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Observed symptoms or test context (optional)"
              aria-label="Recording notes"
              rows={2}
              disabled={agent.status !== "online" || action !== null}
            />
            <button
              type="submit"
              disabled={agent.status !== "online" || action !== null}
            >
              {action === "start" ? "Starting…" : "Start recording"}
            </button>
          </form>
        )}
      </div>

      {error && <div className="recording-error" role="alert">{error}</div>}

      {activeRecording ? (
        <div className="recording-active">
          <div className="recording-live-mark" aria-hidden="true"><i /></div>
          <div className="recording-active-main">
            <div className="recording-active-title">
              <strong>{activeRecording.name}</strong>
              <span className={statusClass(activeRecording.status)}>
                {STATUS_LABELS[activeRecording.status] ?? activeRecording.status}
              </span>
              <span className={syncClass(activeRecording.sync_status)}>
                {SYNC_LABELS[activeRecording.sync_status] ?? activeRecording.sync_status}
              </span>
            </div>
            <span className="recording-active-id">
              {activeRecording.id}
              {activeRecording.max_duration_minutes != null
                && ` · Auto-stop after ${activeRecording.max_duration_minutes} min`}
            </span>
            {(activeRecording.site || activeRecording.location) && (
              <span className="recording-active-place">
                {[activeRecording.site, activeRecording.location].filter(Boolean).join(" · ")}
              </span>
            )}
          </div>
          <div className="recording-stat">
            <span>Elapsed</span>
            <strong>
              {formatDuration(
                activeRecording.started_at,
                activeRecording.ended_at,
                now,
              )}
            </strong>
          </div>
          <div className="recording-stat">
            <span>Metrics</span>
            <strong>{activeRecording.metrics_count.toLocaleString()}</strong>
          </div>
          <div className="recording-stat">
            <span>Events</span>
            <strong>{activeRecording.events_count.toLocaleString()}</strong>
          </div>
          <button
            type="button"
            className="recording-stop"
            onClick={() => void handleStop()}
            disabled={activeRecording.status !== "recording" || action !== null}
          >
            {activeRecording.status === "created"
              ? "Waiting for agent"
              : activeRecording.status === "stopping"
                ? "Stopping…"
                : action === "stop"
                  ? "Stopping…"
                  : "Stop recording"}
          </button>
        </div>
      ) : (
        <div className="recording-ready">
          <div>
            <strong>Ready to record</strong>
            <span>
              {agent.status === "online"
                ? "Start a diagnostic session when you want to preserve detailed evidence."
                : "The Agent must be online before a diagnostic recording can be started."}
            </span>
          </div>
          <span className={agent.status === "online" ? "recording-ready-dot online" : "recording-ready-dot"} />
        </div>
      )}

      <div className="recording-history-heading">
        <div>
          <h3>Recording history</h3>
          <p>Raw captures are retained independently from rolling telemetry.</p>
        </div>
        <span>{recordings.length} total</span>
      </div>

      {loading ? (
        <div className="recording-empty">Loading recordings…</div>
      ) : recordings.length === 0 ? (
        <div className="recording-empty">No diagnostic recordings yet.</div>
      ) : (
        <div className="recording-table-wrap">
          <table className="recording-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Sync</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Metrics</th>
                <th>Events</th>
              </tr>
            </thead>
            <tbody>
              {recordings.map((recording) => (
                <tr key={recording.id}>
                  <td>
                    <button
                      type="button"
                      className="recording-name-link"
                      onClick={() => navigateToRecording(agent.id, recording.id)}
                    >
                      {recording.name}
                    </button>
                    {(recording.site || recording.location) && (
                      <span className="recording-history-place">
                        {[recording.site, recording.location].filter(Boolean).join(" · ")}
                      </span>
                    )}
                    <small>{recording.id}</small>
                  </td>
                  <td>
                    <span className={statusClass(recording.status)}>
                      {STATUS_LABELS[recording.status] ?? recording.status}
                    </span>
                  </td>
                  <td>
                    <span className={syncClass(recording.sync_status)}>
                      {SYNC_LABELS[recording.sync_status] ?? recording.sync_status}
                    </span>
                  </td>
                  <td>{formatDate(recording.started_at ?? recording.created_at)}</td>
                  <td>{formatDuration(recording.started_at, recording.ended_at, now)}</td>
                  <td>{recording.metrics_count.toLocaleString()}</td>
                  <td>{recording.events_count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
