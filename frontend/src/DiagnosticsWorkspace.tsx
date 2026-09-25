import { useEffect, useState } from "react";

import { getAgents } from "./agentApi";
import type { AgentSummary } from "./agentTypes";
import { diagnosticsAgentHash } from "./diagnosticRoutes";
import RecordingPanel from "./RecordingPanel";
import "./DiagnosticsWorkspace.css";

export default function DiagnosticsWorkspace({ agentId }: { agentId: string | null }) {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const data = await getAgents();
        if (active) {
          setAgents(data);
          setLoading(false);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setLoading(false);
          setError(err instanceof Error ? err.message : "Unable to load agents");
        }
      }
    }

    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const selected = agents.find((agent) => agent.id === agentId);

  return (
    <>
      <section className="agent-page-heading diagnostics-page-heading">
        <div>
          <span className="agent-eyebrow">Diagnostics</span>
          <h1>Collections and analysis</h1>
          <p>Select an Agent to capture evidence, review recordings and compare results.</p>
        </div>
        <label htmlFor="diagnostics-agent-picker" className="diagnostics-agent-picker">
          Collection Agent
          <select
            id="diagnostics-agent-picker"
            value={agentId ?? ""}
            onChange={(event) => {
              window.location.hash = event.target.value
                ? diagnosticsAgentHash(event.target.value)
                : "#diagnostics";
            }}
            disabled={loading || agents.length === 0}
          >
            <option value="">Choose an Agent</option>
            {agentId && !selected && <option value={agentId}>Agent unavailable</option>}
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name} · {agent.status === "online" ? "Online" : "Offline"}
              </option>
            ))}
          </select>
        </label>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}
      {loading ? (
        <div className="agent-empty">Loading collection Agents…</div>
      ) : agents.length === 0 ? (
        <div className="agent-empty">No Agents are enrolled yet.</div>
      ) : selected ? (
        <>
          <div className="diagnostics-agent-context">
            <span className={`agent-status ${selected.status === "online" ? "agent-status-online" : "agent-status-offline"}`}>
              <i />{selected.status === "online" ? "Online" : "Offline"}
            </span>
            <span>{selected.hostname}</span>
            <a href={`#agents/${encodeURIComponent(selected.id)}`}>View Agent status and settings</a>
          </div>
          <RecordingPanel key={selected.id} agent={selected} />
        </>
      ) : agentId ? (
        <div className="agent-empty">This Agent is no longer available. Choose another Agent.</div>
      ) : (
        <div className="agent-empty">Choose an Agent to start a collection or review its history.</div>
      )}
    </>
  );
}
