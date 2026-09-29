import { useEffect, useMemo, useState } from "react";

import { getAgentRecordings, startAgentRecording, stopRecording } from "./agentApi";
import type { AgentCurrentState, AgentSummary, DiagnosticRecording, StartRecordingInput } from "./agentTypes";
import CollectionStartForm from "./CollectionStartForm";
import { describeWifiConnection } from "./wifiPresentation";

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);
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
  const activeCollection = activeRecording ?? activeProjectRecording;

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
    if (!activeCollection) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeCollection]);

  async function handleStart(input: StartRecordingInput): Promise<boolean> {
    if (busy || activeRecording || activeProjectRecording || agent.status !== "online") return false;
    setBusy("start");
    setError(null);
    try {
      const recording = await startAgentRecording(agent.id, input);
      setRecordings((current) => [recording, ...current.filter((item) => item.id !== recording.id)]);
      setExpanded(true);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start collection");
      return false;
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
  const wifiPresentation = describeWifiConnection(wifi);
  const collectionBlocked = Boolean(activeProjectRecording) || agent.status !== "online";

  return (
    <article className={`managed-agent-card${activeCollection ? " managed-agent-recording" : ""}`}>
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
          <span>
            <small>Radio</small>
            <strong>{wifi ? `${wifiPresentation.band} · ${wifiPresentation.frequency}` : "—"}</strong>
          </span>
          <span>
            <small>Wi-Fi</small>
            <strong>{wifi ? `${wifiPresentation.generation} · ${wifiPresentation.shorthand}` : "—"}</strong>
          </span>
          <span><small>RSSI</small><strong>{wifi?.rssi_dbm != null ? `${wifi.rssi_dbm.toFixed(0)} dBm` : "—"}</strong></span>
          <span><small>Link score</small><strong>{score != null ? `${score.toFixed(0)}/100` : "—"}</strong></span>
        </div>

        <div className="managed-agent-actions">
          <button type="button" className="managed-agent-secondary" onClick={onOpen}>View details</button>
          {activeCollection ? (
            <button type="button" onClick={() => { window.location.hash = "#diagnostics"; }}>
              Open collection
            </button>
          ) : (
            <button type="button" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded}>
              {expanded ? "Close" : "Start collection"}
            </button>
          )}
        </div>
      </div>

      {error && <div className="managed-agent-error" role="alert">{error}</div>}

      {activeCollection ? (
        <div className="managed-agent-expanded">
          <div className="managed-agent-active-collection">
            <div>
              <span className="agent-eyebrow">
                {activeProjectRecording ? "Project collecting" : "Now collecting"}
              </span>
              <strong>{activeCollection.name}</strong>
              <small>
                {activeProjectRecording
                  ? activeProjectRecording.project_name ?? "Diagnostic project"
                  : [activeCollection.site, activeCollection.location].filter(Boolean).join(" · ")
                    || "No location metadata"}
              </small>
            </div>
            <dl>
              <div><dt>Elapsed</dt><dd>{formatDuration(activeCollection.started_at, activeCollection.ended_at, now)}</dd></div>
              <div><dt>Metrics</dt><dd>{activeCollection.metrics_count.toLocaleString()}</dd></div>
              <div><dt>Events</dt><dd>{activeCollection.events_count.toLocaleString()}</dd></div>
            </dl>
            {activeRecording && (
              <button type="button" className="managed-agent-stop" onClick={() => void handleStop()}
                disabled={activeRecording.status !== "recording" || busy !== null}>
                {busy === "stop" || activeRecording.status === "stopping"
                  ? "Stopping…"
                  : activeRecording.status === "created" ? "Waiting for Agent" : "Stop collection"}
              </button>
            )}
          </div>
        </div>
      ) : expanded ? (
        <div className="managed-agent-expanded">
          <CollectionStartForm
            disabled={collectionBlocked}
            busy={busy === "start"}
            onSubmit={handleStart}
          />
        </div>
      ) : null}
    </article>
  );
}
