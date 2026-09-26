import { useEffect, useMemo, useRef, useState } from "react";

import { deleteRecording, getAgentRecordings, getAgents } from "./agentApi";
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

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);
const DATASETS_PER_PAGE = 15;

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

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5" />
    </svg>
  );
}

export default function DiagnosticsWorkspace({ agentId }: { agentId: string | null }) {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const agentsRef = useRef<AgentSummary[]>([]);
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
  const [datasetPage, setDatasetPage] = useState(1);
  const [selectedDatasetIds, setSelectedDatasetIds] = useState<Set<string>>(new Set());
  const [deletingDatasets, setDeletingDatasets] = useState(false);
  const [launcherOpen, setLauncherOpen] = useState(Boolean(agentId));

  useEffect(() => {
    if (agentId) {
      setDatasetAgentFilter(agentId);
      setLauncherOpen(true);
    }
  }, [agentId]);

  useEffect(() => {
    setDatasetPage(1);
    setSelectedDatasetIds(new Set());
  }, [datasetAgentFilter, datasetSearch, datasetStatusFilter, datasetView]);

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const data = await getAgents();
        if (active) {
          agentsRef.current = data;
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

  const agentIdsKey = useMemo(
    () => agents.map((agent) => agent.id).sort().join("|"),
    [agents],
  );

  useEffect(() => {
    if (loading) return;

    let active = true;
    async function refreshDatasets(): Promise<void> {
      const currentAgents = agentsRef.current;
      if (currentAgents.length === 0) {
        setDatasets([]);
        setRecordingsByAgent({});
        setDatasetsLoading(false);
        return;
      }
      try {
        const results = await Promise.allSettled(
          currentAgents.map(async (agent) => ({ agent, recordings: await getAgentRecordings(agent.id) })),
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

    void refreshDatasets();
    const timer = window.setInterval(() => void refreshDatasets(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [agentIdsKey, loading]);

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

  const pageCount = Math.max(1, Math.ceil(filteredDatasets.length / DATASETS_PER_PAGE));
  const currentPage = Math.min(datasetPage, pageCount);
  const pageStart = (currentPage - 1) * DATASETS_PER_PAGE;
  const paginatedDatasets = filteredDatasets.slice(pageStart, pageStart + DATASETS_PER_PAGE);
  const selectablePageIds = paginatedDatasets
    .filter(({ recording }) => !ACTIVE_STATUSES.has(recording.status))
    .map(({ recording }) => recording.id);
  const allPageSelected = selectablePageIds.length > 0
    && selectablePageIds.every((id) => selectedDatasetIds.has(id));

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
    setLauncherOpen(false);
  }

  function toggleDatasetSelection(recordingId: string): void {
    setSelectedDatasetIds((current) => {
      const next = new Set(current);
      if (next.has(recordingId)) next.delete(recordingId);
      else next.add(recordingId);
      return next;
    });
  }

  function togglePageSelection(): void {
    setSelectedDatasetIds((current) => {
      const next = new Set(current);
      if (allPageSelected) selectablePageIds.forEach((id) => next.delete(id));
      else selectablePageIds.forEach((id) => next.add(id));
      return next;
    });
  }

  async function removeDatasets(recordingIds: string[]): Promise<void> {
    if (recordingIds.length === 0 || deletingDatasets) return;
    setDeletingDatasets(true);
    setDatasetError(null);
    const results = await Promise.allSettled(recordingIds.map((id) => deleteRecording(id)));
    const deletedIds = new Set(
      recordingIds.filter((_, index) => results[index]?.status === "fulfilled"),
    );
    const failedCount = results.length - deletedIds.size;

    if (deletedIds.size > 0) {
      setDatasets((current) => current.filter(({ recording }) => !deletedIds.has(recording.id)));
      setRecordingsByAgent((current) => Object.fromEntries(
        Object.entries(current).map(([id, recordings]) => [
          id,
          recordings.filter((recording) => !deletedIds.has(recording.id)),
        ]),
      ));
      setSelectedDatasetIds((current) => {
        const next = new Set(current);
        deletedIds.forEach((id) => next.delete(id));
        return next;
      });
    }

    if (failedCount > 0) {
      const firstFailure = results.find((result) => result.status === "rejected");
      setDatasetError(
        firstFailure?.status === "rejected" && firstFailure.reason instanceof Error
          ? `${failedCount} dataset${failedCount === 1 ? "" : "s"} could not be deleted: ${firstFailure.reason.message}`
          : `${failedCount} dataset${failedCount === 1 ? "" : "s"} could not be deleted.`,
      );
    }
    setDeletingDatasets(false);
  }

  function confirmSingleDelete(recording: DiagnosticRecording): void {
    if (ACTIVE_STATUSES.has(recording.status)) return;
    if (!window.confirm(
      `Delete dataset "${recording.name}"?\n\nThis permanently removes its metrics, events and analysis data.`,
    )) return;
    void removeDatasets([recording.id]);
  }

  function confirmBulkDelete(): void {
    const ids = [...selectedDatasetIds];
    if (ids.length === 0) return;
    if (!window.confirm(
      `Delete ${ids.length} selected dataset${ids.length === 1 ? "" : "s"}?\n\nThis action is permanent.`,
    )) return;
    void removeDatasets(ids);
  }

  return (
    <>
      <section className="agent-page-heading diagnostics-page-heading">
        <div>
          <span className="agent-eyebrow">Diagnostics</span>
          <h1>Datasets and analysis</h1>
          <p>Investigate captured evidence and start an individual collection when needed.</p>
        </div>
        <button
          type="button"
          className={`diagnostics-launcher-toggle${launcherOpen ? " active" : ""}`}
          aria-expanded={launcherOpen}
          onClick={() => setLauncherOpen((current) => !current)}
        >
          {launcherOpen ? "Close collection form" : "Start collection"}
        </button>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}

      {launcherOpen && (
        <DiagnosticCollectionLauncher
          agents={agents}
          recordingsByAgent={recordingsByAgent}
          initialAgentId={agentId}
          loading={loading}
          onStarted={handleCollectionStarted}
        />
      )}

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
            {selectedDatasetIds.size > 0 && (
              <div className="diagnostics-bulk-actions">
                <span>{selectedDatasetIds.size} selected</span>
                <div>
                  <button type="button" onClick={() => setSelectedDatasetIds(new Set())} disabled={deletingDatasets}>
                    Clear selection
                  </button>
                  <button type="button" className="danger" onClick={confirmBulkDelete} disabled={deletingDatasets}>
                    {deletingDatasets ? "Deleting…" : "Delete selected"}
                  </button>
                </div>
              </div>
            )}
            {datasetError && <div className="diagnostics-error" role="alert">{datasetError}</div>}
            {datasetsLoading ? (
              <div className="agent-empty">Loading individual datasets…</div>
            ) : filteredDatasets.length === 0 ? (
              <div className="agent-empty">No individual datasets match the current filters.</div>
            ) : (
              <>
                <div className="diagnostics-dataset-table-wrap">
                  <table className="diagnostics-dataset-table">
                    <thead>
                      <tr>
                        <th className="diagnostics-select-column">
                          <input
                            type="checkbox"
                            aria-label="Select datasets on this page"
                            checked={allPageSelected}
                            disabled={selectablePageIds.length === 0 || deletingDatasets}
                            onChange={togglePageSelection}
                          />
                        </th>
                        <th>Dataset</th><th>Agent</th><th>Status</th><th>Started</th><th>Duration</th><th>Evidence</th><th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>{paginatedDatasets.map(({ agent, recording }) => {
                      const active = ACTIVE_STATUSES.has(recording.status);
                      return (
                        <tr key={recording.id}>
                          <td className="diagnostics-select-column">
                            <input
                              type="checkbox"
                              aria-label={`Select ${recording.name}`}
                              checked={selectedDatasetIds.has(recording.id)}
                              disabled={active || deletingDatasets}
                              onChange={() => toggleDatasetSelection(recording.id)}
                            />
                          </td>
                          <td><strong>{recording.name}</strong>{(recording.site || recording.location) && <small>{[recording.site, recording.location].filter(Boolean).join(" · ")}</small>}</td>
                          <td><strong>{agent.name}</strong><small>{agent.hostname}</small></td>
                          <td><span className={`diagnostics-status diagnostics-status-${recording.status}`}>{STATUS_LABELS[recording.status] ?? recording.status}</span></td>
                          <td>{formatDate(recording.started_at ?? recording.created_at)}</td>
                          <td>{formatDuration(recording.started_at, recording.ended_at)}</td>
                          <td>{recording.metrics_count.toLocaleString()} metrics · {recording.events_count.toLocaleString()} events</td>
                          <td>
                            <div className="diagnostics-row-actions">
                              {recording.status === "completed" && recording.sync_status === "complete" && (
                                <button type="button" onClick={() => { window.location.hash = diagnosticsRecordingHash(agent.id, recording.id); }}>View analysis</button>
                              )}
                              <button
                                type="button"
                                className="diagnostics-delete-button"
                                aria-label={`Delete ${recording.name}`}
                                title={active ? "Active collections cannot be deleted" : "Delete dataset"}
                                disabled={active || deletingDatasets}
                                onClick={() => confirmSingleDelete(recording)}
                              >
                                <TrashIcon />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}</tbody>
                  </table>
                </div>
                <div className="diagnostics-pagination">
                  <span>
                    Showing {pageStart + 1}–{Math.min(pageStart + DATASETS_PER_PAGE, filteredDatasets.length)} of {filteredDatasets.length}
                  </span>
                  <div>
                    <button type="button" disabled={currentPage <= 1} onClick={() => setDatasetPage(currentPage - 1)}>Previous</button>
                    <span>Page {currentPage} of {pageCount}</span>
                    <button type="button" disabled={currentPage >= pageCount} onClick={() => setDatasetPage(currentPage + 1)}>Next</button>
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </section>
    </>
  );
}
