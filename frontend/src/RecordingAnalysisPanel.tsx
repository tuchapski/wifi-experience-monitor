import { useEffect, useState } from "react";

import {
  getLatestRecordingAnalysis,
  runRecordingAnalysis,
} from "./agentApi";
import type {
  DiagnosticRecording,
  RecordingAnalysis,
} from "./agentTypes";
import "./RecordingAnalysisPanel.css";

function formatDbm(value: number | undefined): string {
  return value == null ? "—" : `${value.toFixed(1)} dBm`;
}

function formatPercent(value: number | undefined): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

function formatPer100(value: number | undefined): string {
  return value == null ? "—" : `${value.toFixed(1)}/100`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

export default function RecordingAnalysisPanel({
  recording,
}: {
  recording: DiagnosticRecording;
}) {
  const [analysis, setAnalysis] = useState<RecordingAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAnalyze = recording.status === "completed"
    && recording.sync_status === "complete";

  useEffect(() => {
    let active = true;
    async function load(): Promise<void> {
      try {
        const result = await getLatestRecordingAnalysis(recording.id);
        if (active) {
          setAnalysis(result);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load analysis");
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [recording.id]);

  async function handleRun(): Promise<void> {
    if (!canAnalyze || running) return;
    setRunning(true);
    setError(null);
    try {
      setAnalysis(await runRecordingAnalysis(recording.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run analysis");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="agent-panel recording-analysis-panel">
      <div className="recording-analysis-heading">
        <div>
          <span className="agent-eyebrow">Analysis</span>
          <h2>Explainable diagnostic findings</h2>
          <p>
            Versioned heuristics derived from the immutable recording dataset.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={!canAnalyze || running}
        >
          {running ? "Analyzing…" : analysis ? "Run again" : "Run analysis"}
        </button>
      </div>

      {error && <div className="recording-analysis-error">{error}</div>}

      {!canAnalyze ? (
        <div className="recording-analysis-empty">
          Analysis becomes available when the recording is completed and fully synchronized.
        </div>
      ) : loading ? (
        <div className="recording-analysis-empty">Loading latest analysis…</div>
      ) : analysis === null ? (
        <div className="recording-analysis-empty">
          <strong>No analysis has been run for this recording.</strong>
          <span>Run the deterministic V1 engine to generate findings.</span>
        </div>
      ) : (
        <>
          <div className="recording-analysis-summary">
            <article>
              <span>Assessment</span>
              <strong className={`analysis-${analysis.summary.status}`}>
                {analysis.summary.status}
              </strong>
            </article>
            <article>
              <span>Evidence</span>
              <strong>{analysis.summary.evidence_status}</strong>
            </article>
            <article>
              <span>RSSI average</span>
              <strong>{formatDbm(analysis.summary.rssi?.average)}</strong>
            </article>
            <article>
              <span>Retries P90</span>
              <strong>{formatPer100(analysis.summary.tx_retries_per_100_packets?.p90)}</strong>
            </article>
            <article>
              <span>TX failures P90</span>
              <strong>{formatPercent(analysis.summary.tx_failed_percent?.p90)}</strong>
            </article>
          </div>

          <div className="recording-analysis-meta">
            <span>Engine <code>{analysis.engine_version}</code></span>
            <span>Analyzed {formatDate(analysis.created_at)}</span>
            <span>
              Source {analysis.source_metrics_count.toLocaleString()} metrics ·{" "}
              {analysis.source_events_count.toLocaleString()} events
            </span>
          </div>

          {analysis.findings.length === 0 ? (
            <div className="recording-analysis-clear">
              <strong>No findings were triggered by this engine version.</strong>
              <span>
                This means the available evidence did not cross the configured
                heuristics; it is not proof that the WLAN is fault-free.
              </span>
            </div>
          ) : (
            <div className="recording-findings">
              {analysis.findings.map((finding) => (
                <article
                  key={finding.code}
                  className={`recording-finding finding-${finding.severity}`}
                >
                  <div>
                    <span>{finding.severity}</span>
                    <code>{finding.code}</code>
                  </div>
                  <h3>{finding.title}</h3>
                  <p>{finding.message}</p>
                  <strong>Next action</strong>
                  <p>{finding.next_action}</p>
                </article>
              ))}
            </div>
          )}

          {analysis.summary.limitations.length > 0 && (
            <div className="recording-analysis-limitations">
              <strong>Analysis limitations</strong>
              <ul>
                {analysis.summary.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
