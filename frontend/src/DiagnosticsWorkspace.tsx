import { useEffect, useState } from "react";

import { getAgents } from "./agentApi";
import type { AgentSummary } from "./agentTypes";
import { diagnosticsAgentHash } from "./diagnosticRoutes";
import DiagnosticProjectsPanel from "./DiagnosticProjectsPanel";
import RecordingPanel from "./RecordingPanel";
import "./DiagnosticsWorkspace.css";

export default function DiagnosticsWorkspace({ agentId }: { agentId: string | null }) {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"projects" | "individual">(
    agentId ? "individual" : "projects",
  );
  const [lastAgentId, setLastAgentId] = useState<string | null>(agentId);

  useEffect(() => {
    if (agentId) {
      setLastAgentId(agentId);
      setView("individual");
    }
  }, [agentId]);

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

  function openProjects(): void {
    setView("projects");
    if (agentId) window.location.hash = "#diagnostics";
  }

  function openIndividual(): void {
    setView("individual");
    if (!agentId && lastAgentId) {
      window.location.hash = diagnosticsAgentHash(lastAgentId);
    }
  }

  return (
    <>
      <section className="agent-page-heading diagnostics-page-heading">
        <div>
          <span className="agent-eyebrow">Diagnostics</span>
          <h1>Collections and analysis</h1>
          <p>Choose how you want to collect evidence.</p>
        </div>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}
      <nav className="diagnostics-workflows" aria-label="Collection workflows">
        <button type="button" className={view === "projects" ? "active" : ""}
          aria-pressed={view === "projects"} onClick={openProjects}>
          <strong>Projects</strong>
          <span>Plan and run collections with one or more Agents</span>
        </button>
        <button type="button" className={view === "individual" ? "active" : ""}
          aria-pressed={view === "individual"} onClick={openIndividual}>
          <strong>Individual collection</strong>
          <span>Record and review evidence from a single Agent</span>
        </button>
      </nav>

      {view === "projects" ? (
        loading ? <div className="agent-empty">Loading collection Agents…</div>
          : <DiagnosticProjectsPanel agents={agents} />
      ) : (
        <section className="diagnostics-individual" aria-labelledby="individual-title">
          <div className="diagnostics-individual-heading">
            <div>
              <span className="agent-eyebrow">Individual collection</span>
              <h2 id="individual-title">Record with one Agent</h2>
              <p>Select an Agent to start a recording or review its history.</p>
            </div>
            <label htmlFor="diagnostics-agent-picker" className="diagnostics-agent-picker">
              Agent
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
          </div>
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
            <div className="agent-empty">Choose an Agent to start or review a recording.</div>
          )}
        </section>
      )}
    </>
  );
}
