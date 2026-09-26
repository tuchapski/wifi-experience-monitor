import { useEffect, useMemo, useState } from "react";

import { getAgentRecordings, getAgents } from "./agentApi";
import type { AgentSummary, DiagnosticRecording } from "./agentTypes";
import { diagnosticsRecordingHash } from "./diagnosticRoutes";
import DiagnosticCollectionLauncher from "./DiagnosticCollectionLauncher";
import DiagnosticProjectsPanel from "./DiagnosticProjectsPanel";
import "./DiagnosticsWorkspace.css";

const STATUS_LABELS: Record<string, string> = {
  created: "Waiting for agent",
  recording: "Recording",
  stopping: "Stopping",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

interface IndividualDataset {
  agent: AgentSummary;
  recording: DiagnosticRecording;
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const startTime = Date.parse(start);
  const endTime = end ? Date.parse(end) : Date.now();
  const seconds = Math.max(0, Math.floor((endTime - startTime) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${seconds}s`;
}

export default function DiagnosticsWorkspace({ agentId }: { agentId: string | null }) {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [datasets, setDatasets] = useState<IndividualDataset[]>([]);
  const [recordingsByAgent, setRecordingsByAgent] = useState<Record<string, DiagnosticRecording[]>>({});
  const [loading, setLoading] = useState(true);
  const [datasetsLoading, setDatasetsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [datasetView, setDatasetView] = useState<"individual" | "projects">("individual");
  const [datasetAgentFilter, setDatasetAgentFilter] = useState(agentId ?? "");
  const [datasetStatusFilter, setDatasetStatusFilter] = useState("");
  const [datasetSearch, setDatasetSearch] = useState("");

  useEffect(() => {
    if (agentId) setDatasetAgentFilter(agentId);
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

  useEffect(() => {
    let active = true;
    async function refreshDatasets(): Promise<void> {
      if (agents.length === 0) {
        setDatasets([]);
        setRecordingsByAgent({});
        setDatasetsLoading(false);
        return;
      }
      try {
        const results = await Promise.allSettled(
          agents.map(async (agent) => ({ agent, recordings: await getAgentRecordings(agent.id) })),
        );
        if (!active) return;
        const recordingMap: Record<string, DiagnosticRecording[]> = {};
        const loaded = results.flatMap((result) => {
          if (result.status !== "fulfilled") return [];
          recordingMap[result.value.agent.id] = result.value.recordings;
          return result.value.recordings
            .filter((recording) => !recording.project_run_id)
            .map((recording) => ({ agent: result.value.agent, recording }));
        });
        setRecordingsByAgent(recordingMap);
        setDatasets(loaded);
        setDatasetError(results.some((result) => result.status === "rejected")
          ? "Some Agent datasets could not be loaded. Available datasets are shown below."
          : null);
      } catch (err) {
        if (active) {
          setDatasetError(err instanceof Error ? err.message : "Unable to load individual datasets");
        }
      } finally {
        if (active) setDatasetsLoading(false);
      }
    }

    setDatasetsLoading(true);
    void refreshDatasets();
    const timer = window.setInterval(() => void refreshDatasets(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [agents]);

  const statuses = useMemo(
    () => [...new Set(datasets.map(({ recording }) => recording.status))].sort(),
    [datasets],
  );
  const filteredDatasets = useMemo(() => {
    const search = datasetSearch.trim().toLowerCase();
    return datasets
      .filter(({ agent }) => !datasetAgentFilter || agent.id === datasetAgentFilter)
      .filter(({ recording }) => !datasetStatusFilter || recording.status === datasetStatusFilter)
      .filter(({ agent, recording }) => !search || [
        recording.name,
        recording.site,
        recording.location,
        recording.description,
        agent.name,
        agent.hostname,
      ].some((value) => value?.toLowerCase().includes(search)))
      .sort((left, right) => Date.parse(right.recording.started_at ?? right.recording.created_at)
        - Date.parse(left.recording.started_at ?? left.recording.created_at));
  }, [datasetAgentFilter, datasetSearch, datasetStatusFilter, datasets]);

  function handleCollectionStarted(agent: AgentSummary, recording: DiagnosticRecording): void {
    setRecordingsByAgent((current) => ({
      ...current,
      [agent.id]: [
        recording,
        ...(current[agent.id] ?? []).filter((item) => item.id !== recording.id),
      ],
    }));
    if (!recording.project_run_id) {
      setDatasets((current) => [
        { agent, recording },
        ...current.filter((item) => item.recording.id !== recording.id),
      ]);
    }
  }

  return (
    <>
      <section className="agent-page-heading diagnostics-page-heading">
        <div>
          <span className="agent-eyebrow">Diagnostics</span>
          <h1>Datasets and analysis</h1>
          <p>Investigate captured evidence and start an individual collection when needed.</p>
        </div>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}

      <section className="diagnostics-datasets" aria-labelledby="datasets-title">
        <div className="diagnostics-datasets-heading">
          <div>
            <span className="agent-eyebrow">Recorded evidence</span>
            <h2 id="datasets-title">Datasets</h2>
            <p>Browse collected evidence independently from the Agent used to capture it.</p>
          </div>
          <nav className="diagnostics-dataset-tabs" aria-label="Dataset type">
            <button type="button" className={datasetView === "individual" ? "active" : ""}
              aria-pressed={datasetView === "individual"} onClick={() => setDatasetView("individual")}>
              Individual
            </button>
            <button type="button" className={datasetView === "projects" ? "active" : ""}
              aria-pressed={datasetView === "projects"} onClick={() => setDatasetView("projects")}>
              Projects
            </button>
          </nav>
        </div>

        {datasetView === "projects" ? (
          loading ? <div className="agent-empty">Loading collection Agents…</div>
            : <DiagnosticProjectsPanel agents={agents} />
        ) : (
          <>
            <div className="diagnostics-dataset-filters">
              <label>Agent
                <select value={datasetAgentFilter} onChange={(event) => setDatasetAgentFilter(event.target.value)}>
                  <option value="">All agents</option>
                  {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
                </select>
              </label>
              <label>Status
                <select value={datasetStatusFilter} onChange={(event) => setDatasetStatusFilter(event.target.value)}>
                  <option value="">All statuses</option>
                  {statuses.map((status) => <option key={status} value={status}>{STATUS_LABELS[status] ?? status}</option>)}
                </select>
              </label>
              <label className="diagnostics-dataset-search">Search
                <input type="search" value={datasetSearch} onChange={(event) => setDatasetSearch(event.target.value)}
                  placeholder="Name, site, location or Agent" />
              </label>
            </div>
            {datasetError && <div className="diagnostics-error" role="alert">{datasetError}</div>}
            {datasetsLoading ? (
              <div className="agent-empty">Loading individual datasets…</div>
            ) : filteredDatasets.length === 0 ? (
              <div className="agent-empty">No individual datasets match the current filters.</div>
            ) : (
              <div className="diagnostics-dataset-table-wrap">
                <table className="diagnostics-dataset-table">
                  <thead><tr><th>Dataset</th><th>Agent</th><th>Status</th><th>Started</th><th>Duration</th><th>Evidence</th><th /></tr></thead>
                  <tbody>{filteredDatasets.map(({ agent, recording }) => (
                    <tr key={recording.id}>
                      <td><strong>{recording.name}</strong>{(recording.site || recording.location) && <small>{[recording.site, recording.location].filter(Boolean).join(" · ")}</small>}</td>
                      <td><strong>{agent.name}</strong><small>{agent.hostname}</small></td>
                      <td><span className={`diagnostics-status diagnostics-status-${recording.status}`}>{STATUS_LABELS[recording.status] ?? recording.status}</span></td>
                      <td>{formatDate(recording.started_at ?? recording.created_at)}</td>
                      <td>{formatDuration(recording.started_at, recording.ended_at)}</td>
                      <td>{recording.metrics_count.toLocaleString()} metrics · {recording.events_count.toLocaleString()} events</td>
                      <td>{recording.status === "completed" && recording.sync_status === "complete" && (
                        <button type="button" onClick={() => { window.location.hash = diagnosticsRecordingHash(agent.id, recording.id); }}>View analysis</button>
                      )}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

      <DiagnosticCollectionLauncher
        agents={agents}
        recordingsByAgent={recordingsByAgent}
        initialAgentId={agentId}
        loading={loading}
        onStarted={handleCollectionStarted}
      />
    </>
  );
}
