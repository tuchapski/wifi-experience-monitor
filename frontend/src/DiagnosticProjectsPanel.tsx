import { type FormEvent, useEffect, useState } from "react";

import {
  createDiagnosticProject,
  getDiagnosticProjects,
  startDiagnosticProjectRun,
  stopRecording,
} from "./agentApi";
import type { AgentSummary, DiagnosticProject } from "./agentTypes";
import ProjectRunOverview from "./ProjectRunOverview";
import "./DiagnosticProjectsPanel.css";

const DURATIONS = [15, 30, 60, 120, 240, 480, 1440];

export default function DiagnosticProjectsPanel({ agents }: { agents: AgentSummary[] }) {
  const [projects, setProjects] = useState<DiagnosticProject[]>([]);
  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [site, setSite] = useState("");
  const [location, setLocation] = useState("");
  const [agentIds, setAgentIds] = useState<string[]>([]);
  const [agentLocations, setAgentLocations] = useState<Record<string, string>>({});
  const [duration, setDuration] = useState(60);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  async function refresh(): Promise<void> {
    try {
      const data = await getDiagnosticProjects();
      setProjects(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load diagnostic projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function poll(): Promise<void> {
      try {
        const data = await getDiagnosticProjects();
        if (active) {
          setProjects(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load diagnostic projects");
          setLoading(false);
        }
      }
    }
    void poll();
    const timer = window.setInterval(() => void poll(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  function toggleAgent(id: string): void {
    setAgentIds((current) => current.includes(id)
      ? current.filter((item) => item !== id)
      : [...current, id]);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!name.trim() || agentIds.length === 0 || busy) return;
    setBusy("create");
    setError(null);
    try {
      await createDiagnosticProject({
        name: name.trim(),
        objective: objective.trim() || null,
        site: site.trim() || null,
        location: location.trim() || null,
        agent_ids: agentIds,
        agent_locations: Object.fromEntries(agentIds
          .filter((id) => agentLocations[id]?.trim())
          .map((id) => [id, agentLocations[id].trim()])),
        profile_id: "wifi-deep-dive",
        max_duration_minutes: duration,
      });
      setName("");
      setObjective("");
      setSite("");
      setLocation("");
      setAgentIds([]);
      setAgentLocations({});
      setShowCreate(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create project");
    } finally {
      setBusy(null);
    }
  }

  async function handleStart(projectId: string): Promise<void> {
    if (busy) return;
    setBusy(projectId);
    setError(null);
    try {
      await startDiagnosticProjectRun(projectId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start collection run");
    } finally {
      setBusy(null);
    }
  }

  async function handleStop(recordingId: string): Promise<void> {
    if (busy) return;
    setBusy(recordingId);
    setError(null);
    try {
      await stopRecording(recordingId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to stop recording");
    } finally {
      setBusy(null);
    }
  }

  const agentName = (id: string) => agents.find((agent) => agent.id === id)?.name ?? id;

  return (
    <section className="agent-panel diagnostic-projects" aria-labelledby="projects-title">
      <div className="agent-panel-heading">
        <div>
          <span className="agent-eyebrow">Projects</span>
          <h2 id="projects-title">Diagnostic projects</h2>
          <p>Group collections from one or more Agents. Analysis starts after each recording finishes syncing.</p>
        </div>
        <button type="button" className="diagnostic-project-new"
          aria-expanded={showCreate}
          onClick={() => setShowCreate((current) => !current)}>
          {showCreate ? "Close form" : "New project"}
        </button>
      </div>

      {showCreate && (
        <form className="diagnostic-project-form diagnostic-project-create"
          onSubmit={(event) => void handleCreate(event)}>
          <div>
            <h3>Create a project</h3>
            <p>Set up the collection once, then start a run from the project list below.</p>
          </div>
          <div className="diagnostic-project-fields">
            <label>Project name
              <input required maxLength={128} value={name} onChange={(event) => setName(event.target.value)} disabled={busy !== null} placeholder="Office Wi-Fi baseline" />
            </label>
            <label>Maximum duration
              <select value={duration} onChange={(event) => setDuration(Number(event.target.value))} disabled={busy !== null}>
                {DURATIONS.map((minutes) => <option key={minutes} value={minutes}>{minutes} min</option>)}
              </select>
            </label>
            <label>Site (optional)
              <input maxLength={255} value={site} onChange={(event) => setSite(event.target.value)} disabled={busy !== null} />
            </label>
            <label>Default location (optional)
              <input maxLength={255} value={location} onChange={(event) => setLocation(event.target.value)} disabled={busy !== null} />
            </label>
          </div>
          <label>Objective or observed symptoms (optional)
            <textarea maxLength={2000} rows={2} value={objective} onChange={(event) => setObjective(event.target.value)} disabled={busy !== null} />
          </label>
          <fieldset disabled={busy !== null || agents.length === 0}>
            <legend>Collection Agents (choose one or more)</legend>
            <p>Give each Agent a position. Blank positions use the default location above.</p>
            <div className="diagnostic-project-agent-list">
              {agents.map((agent) => (
                <div className="diagnostic-project-agent-row" key={agent.id}>
                  <label>
                    <input type="checkbox" checked={agentIds.includes(agent.id)} onChange={() => toggleAgent(agent.id)} />
                    {agent.name} <small>({agent.status})</small>
                  </label>
                  {agentIds.includes(agent.id) && (
                    <label>Position for {agent.name} (optional)
                      <input maxLength={255} value={agentLocations[agent.id] ?? ""}
                        onChange={(event) => setAgentLocations((current) => ({
                          ...current, [agent.id]: event.target.value,
                        }))} placeholder="e.g. Meeting room · west side" />
                    </label>
                  )}
                </div>
              ))}
              {agents.length === 0 && <span>No Agents available.</span>}
            </div>
          </fieldset>
          <div className="diagnostic-project-actions">
            <small>Capture profile: Wi-Fi deep dive. Collection begins when each Agent accepts its command.</small>
            <button type="submit" disabled={!name.trim() || agentIds.length === 0 || busy !== null}>
              {busy === "create" ? "Creating…" : "Create project"}
            </button>
          </div>
        </form>
      )}

      {error && <div className="recording-error" role="alert">{error}</div>}
      <div className="diagnostic-project-history">
        <h3>Your projects</h3>
        {loading ? <p>Loading projects…</p> : projects.length === 0 ? (
          <p>No projects yet. Create one to organize and run a collection.</p>
        ) : (
          projects.map((project) => {
            const allOnline = project.agent_ids.every((id) =>
              agents.find((agent) => agent.id === id)?.status === "online");
            const activeRun = project.runs.some((run) => run.recordings.some((item) =>
              ["created", "recording", "stopping"].includes(item.status ?? "")));
            return (
              <article key={project.id} className="diagnostic-project-card">
                <div className="diagnostic-project-card-header">
                  <div>
                    <strong>{project.name}</strong>
                    <p>{project.objective ?? "No objective provided"}</p>
                    <small>{[project.site, project.location].filter(Boolean).join(" · ") || "No location"} · {project.max_duration_minutes} min · {project.profile_id}</small>
                    <small>Agents: {project.agent_ids.map((id) =>
                      [agentName(id), project.agent_locations[id]].filter(Boolean).join(" · ")).join(", ")}</small>
                  </div>
                  <button type="button" disabled={!allOnline || activeRun || busy !== null} onClick={() => void handleStart(project.id)}>
                    {busy === project.id ? "Queuing…" : "Start project run"}
                  </button>
                </div>
                {!allOnline && <p className="diagnostic-project-help">All selected Agents must be online before starting a run.</p>}
                {activeRun && <p className="diagnostic-project-help">Finish the current recordings before starting this project again.</p>}
                {project.runs.map((run) => (
                  <ProjectRunOverview key={run.id} run={run} agentName={agentName}
                    busy={busy} onStop={(recordingId) => void handleStop(recordingId)} />
                ))}
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}
