import { useMemo, useState } from "react";

import { startAgentRecording } from "./agentApi";
import type { AgentSummary, DiagnosticRecording, StartRecordingInput } from "./agentTypes";
import CollectionStartForm from "./CollectionStartForm";
import { diagnosticsRecordingHash } from "./diagnosticRoutes";

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);

export default function DiagnosticCollectionLauncher({
  agents,
  recordingsByAgent,
  selectedAgentId,
  onSelectedAgentChange,
  recordingsLoading,
  loading,
  onStarted,
}: {
  agents: AgentSummary[];
  recordingsByAgent: Record<string, DiagnosticRecording[]>;
  selectedAgentId: string;
  onSelectedAgentChange: (agentId: string) => void;
  recordingsLoading: boolean;
  loading: boolean;
  onStarted: (agent: AgentSummary, recording: DiagnosticRecording) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = agents.find((agent) => agent.id === selectedAgentId) ?? null;
  const recordings = selected ? recordingsByAgent[selected.id] ?? [] : [];
  const activeRecording = useMemo(
    () => recordings.find((recording) => ACTIVE_STATUSES.has(recording.status)) ?? null,
    [recordings],
  );
  const blocked = loading || recordingsLoading || !selected || selected.status !== "online" || Boolean(activeRecording);

  async function handleStart(input: StartRecordingInput): Promise<boolean> {
    if (!selected || blocked || busy) return false;
    setBusy(true);
    setError(null);
    try {
      const recording = await startAgentRecording(selected.id, input);
      onStarted(selected, recording);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start collection");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="diagnostics-launcher" aria-labelledby="collection-title">
      <div className="diagnostics-launcher-heading">
        <div>
          <span className="agent-eyebrow">Start collection</span>
          <h2 id="collection-title">Individual diagnostic collection</h2>
          <p>Start here or from the Agent. Active collections remain visible in Diagnostics.</p>
        </div>
        <label htmlFor="diagnostics-agent-picker" className="diagnostics-agent-picker">
          Collection Agent
          <select
            id="diagnostics-agent-picker"
            value={selectedAgentId}
            onChange={(event) => {
              onSelectedAgentChange(event.target.value);
              setError(null);
            }}
            disabled={loading || agents.length === 0}
          >
            <option value="">Choose an Agent</option>
            {selectedAgentId && !selected && <option value={selectedAgentId}>Agent unavailable</option>}
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name} · {agent.status === "online" ? "Online" : "Offline"}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <div className="agent-empty agent-empty-compact">Loading collection Agents…</div>
      ) : agents.length === 0 ? (
        <div className="agent-empty agent-empty-compact">No Agents are enrolled yet.</div>
      ) : selected ? (
        <div className="diagnostics-launcher-body">
          <div className="diagnostics-launcher-context">
            <span className={`agent-status ${selected.status === "online" ? "agent-status-online" : "agent-status-offline"}`}>
              <i />{selected.status === "online" ? "Online" : "Offline"}
            </span>
            <span>{selected.hostname}</span>
            <a href={`#agents/${encodeURIComponent(selected.id)}`}>Open Managed Agent</a>
          </div>

          {activeRecording ? (
            <div className="diagnostics-launcher-notice">
              <div>
                <strong>
                  {activeRecording.project_run_id
                    ? "This Agent is collecting for a diagnostic project."
                    : "This Agent already has an active individual collection."}
                </strong>
                <span>Open the recording to monitor progress or stop it.</span>
              </div>
              <a href={diagnosticsRecordingHash(selected.id, activeRecording.id)}>View active collection</a>
            </div>
          ) : (
            <CollectionStartForm
              disabled={blocked}
              busy={busy}
              onSubmit={handleStart}
            />
          )}
        </div>
      ) : (
        <div className="agent-empty agent-empty-compact">Choose an Agent to start an individual collection.</div>
      )}

      {error && <div className="diagnostics-error" role="alert">{error}</div>}
    </section>
  );
}
