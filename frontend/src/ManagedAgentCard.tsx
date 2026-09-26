import { type FormEvent, useEffect, useMemo, useState } from "react";

import { getAgentRecordings, startAgentRecording, stopRecording } from "./agentApi";
import type { AgentCurrentState, AgentSummary, DiagnosticRecording } from "./agentTypes";

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);
const DURATIONS = [15, 30, 60, 120, 240, 480, 1440];

function formatDuration(start: string | null, end: string | null, now: number): string {
  if (!start) return "—";
  const seconds = Math.max(0, Math.floor(((end ? Date.parse(end) : now) - Date.parse(start)) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${remainder}s`;
  if (minutes > 0) return `${minutes}m ${remainder}s`;
  return `${remainder}s`;
}

export default function ManagedAgentCard({
  agent,
  state,
  stateFresh,
  onOpen,
}: {
  agent: AgentSummary;
  state: AgentCurrentState | null;
  stateFresh: boolean;
  onOpen: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [recordings, setRecordings] = useState<DiagnosticRecording[]>([]);
  const [name, setName] = useState("");
  const [site, setSite] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [duration, setDuration] = useState(60);
  const [busy, setBusy] = useState<"start" | "stop" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const activeRecording = useMemo(
    () => recordings.find((recording) => !recording.project_run_id && ACTIVE_STATUSES.has(recording.status)) ?? null,
    [recordings],
  );
  const activeProjectRecording = useMemo(
    () => recordings.find((recording) => recording.project_run_id && ACTIVE_STATUSES.has(recording.status)) ?? null,
    [recordings],
  );

  useEffect(() => {
    let active = true;
    async function refresh(): Promise<void> {
      try {
        const data = await getAgentRecordings(agent.id);
        if (active) {
          setRecordings(data);
          setError(null);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Unable to load collections");
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
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
    if (busy || activeRecording || activeProjectRecording || agent.status !== "online") return;
    setBusy("start");
    setError(null);
    try {
      const recording = await startAgentRecording(agent.id, {
        name: name.trim() || `Diagnostic ${new Date().toLocaleString()}`,
        description: notes.trim() || null,
        site: site.trim() || null,
        location: location.trim() || null,
        profile_id: "wifi-deep-dive",
        max_duration_minutes: duration,
      });
      setRecordings((current) => [recording, ...current.filter((item) => item.id !== recording.id)]);
      setName("");
      setSite("");
      setLocation("");
      setNotes("");
      setExpanded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start collection");
    } finally {
      setBusy(null);
    }
  }

  async function handleStop(): Promise<void> {
    if (!activeRecording || activeRecording.status !== "recording" || busy) return;
    setBusy("stop");
    setError(null);
    try {
      const recording = await stopRecording(activeRecording.id);
      setRecordings((current) => current.map((item) => item.id === recording.id ? recording : item));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to stop collection");
    } finally {
      setBusy(null);
    }
  }

  const wifi = stateFresh ? state?.wifi : null;
  const score = wifi?.link_score?.value;
  const collectionBlocked = Boolean(activeProjectRecording) || agent.status !== "online";

  return (
    <article className={`managed-agent-card${activeRecording ? " managed-agent-recording" : ""}`}>
      <div className="managed-agent-card-main">
        <div className="managed-agent-identity">
          <div>
            <strong>{agent.name}</strong>
            <small>{agent.hostname} · {agent.agent_type}</small>
          </div>
          <span className={`agent-status ${agent.status === "online" ? "agent-status-online" : "agent-status-offline"}`}>
            <i />{agent.status === "online" ? "Online" : "Offline"}
          </span>
        </div>

        <div className="managed-agent-live">
          <span><small>SSID</small><strong>{wifi?.ssid ?? "—"}</strong></span>
          <span><small>RSSI</small><strong>{wifi?.rssi_dbm != null ? `${wifi.rssi_dbm.toFixed(0)} dBm` : "—"}</strong></span>
          <span><small>Channel</small><strong>{wifi?.channel ?? "—"}</strong></span>
          <span><small>Link score</small><strong>{score != null ? `${score.toFixed(0)}/100` : "—"}</strong></span>
        </div>

        <div className="managed-agent-actions">
          <button type="button" className="managed-agent-secondary" onClick={onOpen}>View details</button>
          <button type="button" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded}>
            {expanded ? "Close" : activeRecording ? "Collection details" : "Start collection"}
          </button>
        </div>
      </div>

      {activeProjectRecording && (
        <div className="managed-agent-notice">
          This Agent is collecting for a diagnostic project. Individual collection is unavailable.
        </div>
      )}
      {error && <div className="managed-agent-error" role="alert">{error}</div>}

      {expanded && (
        <div className="managed-agent-expanded">
          {activeRecording ? (
            <div className="managed-agent-active-collection">
              <div>
                <span className="agent-eyebrow">Active collection</span>
                <strong>{activeRecording.name}</strong>
                <small>{[activeRecording.site, activeRecording.location].filter(Boolean).join(" · ") || "No location metadata"}</small>
              </div>
              <dl>
                <div><dt>Status</dt><dd>{activeRecording.status}</dd></div>
                <div><dt>Elapsed</dt><dd>{formatDuration(activeRecording.started_at, activeRecording.ended_at, now)}</dd></div>
                <div><dt>Metrics</dt><dd>{activeRecording.metrics_count.toLocaleString()}</dd></div>
                <div><dt>Events</dt><dd>{activeRecording.events_count.toLocaleString()}</dd></div>
              </dl>
              <button type="button" className="managed-agent-stop" onClick={() => void handleStop()}
                disabled={activeRecording.status !== "recording" || busy !== null}>
                {busy === "stop" || activeRecording.status === "stopping"
                  ? "Stopping…"
                  : activeRecording.status === "created" ? "Waiting for Agent" : "Stop collection"}
              </button>
            </div>
          ) : (
            <form className="managed-agent-collection-form" onSubmit={(event) => void handleStart(event)}>
              <div className="managed-agent-form-grid">
                <label>Collection name
                  <input maxLength={255} value={name} onChange={(event) => setName(event.target.value)} placeholder="Optional collection name" disabled={collectionBlocked || busy !== null} />
                </label>
                <label>Maximum duration
                  <select value={duration} onChange={(event) => setDuration(Number(event.target.value))} disabled={collectionBlocked || busy !== null}>
                    {DURATIONS.map((minutes) => <option key={minutes} value={minutes}>{minutes} min</option>)}
                  </select>
                </label>
                <label>Site
                  <input maxLength={255} value={site} onChange={(event) => setSite(event.target.value)} placeholder="Optional" disabled={collectionBlocked || busy !== null} />
                </label>
                <label>Location
                  <input maxLength={255} value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Floor / room (optional)" disabled={collectionBlocked || busy !== null} />
                </label>
              </div>
              <label>Observed symptoms or test context
                <textarea maxLength={2000} rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional notes" disabled={collectionBlocked || busy !== null} />
              </label>
              <div className="managed-agent-form-actions">
                <small>Capture profile: Wi-Fi deep dive</small>
                <button type="submit" disabled={collectionBlocked || busy !== null}>
                  {busy === "start" ? "Starting…" : "Start collection"}
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </article>
  );
}
