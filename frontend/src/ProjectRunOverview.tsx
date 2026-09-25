import { recordingReportUrl } from "./agentApi";
import type { DiagnosticProjectRecording, DiagnosticProjectRun } from "./agentTypes";
import { diagnosticsRecordingHash } from "./diagnosticRoutes";
import "./ProjectRunOverview.css";

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);

function recordingState(item: DiagnosticProjectRecording): string {
  if (!item.recording_id || item.status === null) return "Recording unavailable";
  if (item.status === "failed") return "Collection failed";
  if (item.status === "cancelled") return "Collection cancelled";
  if (item.status === "created") return "Waiting for Agent";
  if (item.status === "recording") return "Collecting";
  if (item.status === "stopping") return "Stopping";
  if (item.sync_status === "incomplete" || item.sync_status === "failed") {
    return "Incomplete dataset";
  }
  if (item.sync_status !== "complete") return "Synchronizing";
  return item.analysis ? "Analyzed" : "Analysis pending";
}

export default function ProjectRunOverview({
  run,
  agentName,
  busy,
  onStop,
}: {
  run: DiagnosticProjectRun;
  agentName: (agentId: string) => string;
  busy: string | null;
  onStop: (recordingId: string) => void;
}) {
  const analyzed = run.recordings.filter((item) => item.analysis !== null).length;
  const collecting = run.recordings.filter((item) => ACTIVE_STATUSES.has(item.status ?? "")).length;
  const versions = new Set(run.recordings.flatMap((item) =>
    item.analysis ? [item.analysis.engine_version] : []));

  return (
    <section className="diagnostic-project-run" aria-label={`Run ${new Date(run.started_at).toLocaleString()}`}>
      <div className="project-run-heading">
        <div>
          <span className="agent-eyebrow">Project run</span>
          <h4>{new Date(run.started_at).toLocaleString()}</h4>
        </div>
        <strong>{analyzed} / {run.recordings.length} Agent analyses ready</strong>
      </div>
      <progress value={analyzed} max={run.recordings.length || 1} aria-label="Analyzed Agents" />
      <p className="project-run-context">
        {collecting > 0 && `${collecting} still collecting. `}
        Findings below describe each Agent separately; there is no project-wide diagnosis.
      </p>
      {versions.size > 1 && (
        <p className="project-run-caution">Analysis engine versions differ between Agents.</p>
      )}
      <div className="project-run-members">
        {run.recordings.map((item) => {
          const state = recordingState(item);
          const analysis = item.analysis;
          return (
            <article key={item.agent_id} className="project-run-member">
              <div className="project-run-member-heading">
                <strong>{agentName(item.agent_id)}</strong>
                <span>{state}</span>
              </div>
              {analysis ? (
                <div className="project-run-analysis">
                  <div className="project-run-analysis-meta">
                    <strong className={`project-run-assessment assessment-${analysis.assessment}`}>
                      {analysis.assessment}
                    </strong>
                    <span>Evidence: {analysis.evidence_status}</span>
                  </div>
                  {analysis.top_findings.length > 0 ? (
                    <ul>
                      {analysis.top_findings.map((finding) => (
                        <li key={finding.code}>
                          <span className={`project-run-severity severity-${finding.severity}`}>
                            {finding.severity}
                          </span>
                          {finding.title}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No heuristic findings in the available evidence.</p>
                  )}
                  {analysis.findings_count > analysis.top_findings.length && (
                    <small>{analysis.findings_count - analysis.top_findings.length} more findings</small>
                  )}
                  <small>Engine: {analysis.engine_version}</small>
                </div>
              ) : (
                <p className="project-run-waiting">
                  {state === "Analysis pending"
                    ? "Analysis starts automatically after sync. Open the recording to run it manually if needed."
                    : state === "Incomplete dataset"
                      ? "The recording cannot be analyzed until its dataset is complete."
                      : state === "Collection failed" || state === "Collection cancelled"
                        ? "This collection ended without an analyzable dataset."
                        : "Analysis is available after this Agent finishes and syncs its recording."}
                </p>
              )}
              <div className="project-run-member-actions">
                {item.recording_id && item.status && (
                  <a href={diagnosticsRecordingHash(item.agent_id, item.recording_id)}>
                    {analysis ? "Open analysis" : "View recording"}
                  </a>
                )}
                {item.recording_id && item.status
                  && !ACTIVE_STATUSES.has(item.status) && (
                    <a href={recordingReportUrl(item.recording_id)} download>HTML report</a>
                )}
                {item.recording_id && item.status === "recording" && (
                  <button type="button" className="diagnostic-project-stop" disabled={busy !== null}
                    onClick={() => {
                      if (item.recording_id) onStop(item.recording_id);
                    }}>
                    {busy === item.recording_id ? "Stopping…" : "Stop recording"}
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
