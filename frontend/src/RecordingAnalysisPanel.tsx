import { useEffect, useState } from "react";

import {
  getLatestRecordingAnalysis,
  runRecordingAnalysis,
} from "./agentApi";
import type {
  AnalysisDegradedWindow,
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

function formatClock(value: string): string {
  return new Date(value).toLocaleTimeString();
}

function metricOrDash(value: number | null, suffix: string): string {
  return value == null ? "—" : `${value.toFixed(1)}${suffix}`;
}

const BSSID_METRICS = [
  { key: "wifi.rssi_dbm", label: "RSSI", unit: "dBm" },
  { key: "wifi.tx_retries_per_100_packets", label: "TX retries", unit: "/100" },
  { key: "wifi.channel_utilization_percent", label: "Channel utilization", unit: "%" },
] as const;

export default function RecordingAnalysisPanel({
  recording,
  selectedWindow,
  onSelectWindow,
  onWindowsChange,
}: {
  recording: DiagnosticRecording;
  selectedWindow: AnalysisDegradedWindow | null;
  onSelectWindow: (window: AnalysisDegradedWindow) => void;
  onWindowsChange: (windows: AnalysisDegradedWindow[]) => void;
}) {
  const [analysis, setAnalysis] = useState<RecordingAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAnalyze = recording.status === "completed"
    && recording.sync_status === "complete";
  const waitingForAutomaticAnalysis = canAnalyze && analysis === null;

  useEffect(() => {
    let active = true;
    async function load(): Promise<void> {
      try {
        const result = await getLatestRecordingAnalysis(recording.id);
        if (active) {
          setAnalysis(result);
          onWindowsChange(result?.summary.degraded_windows ?? []);
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
    const timer = waitingForAutomaticAnalysis
      ? window.setInterval(() => void load(), 5000) : null;
    return () => {
      active = false;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [onWindowsChange, recording.id, waitingForAutomaticAnalysis]);

  async function handleRun(): Promise<void> {
    if (!canAnalyze || running) return;
    setRunning(true);
    setError(null);
    try {
      const result = await runRecordingAnalysis(recording.id);
      setAnalysis(result);
      onWindowsChange(result.summary.degraded_windows ?? []);
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
          <strong>Automatic analysis pending.</strong>
          <span>The Server retries pending analyses after interruptions. You can also run it now.</span>
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
              <span>Channel util P90</span>
              <strong>{formatPercent(analysis.summary.channel_utilization_percent?.p90)}</strong>
            </article>
            <article>
              <span>TX failures P90</span>
              <strong>{formatPercent(analysis.summary.tx_failed_percent?.p90)}</strong>
            </article>
            <article>
              <span>Degraded windows</span>
              <strong>{analysis.summary.degraded_windows?.length ?? 0}</strong>
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

          {analysis.summary.collection_integrity && (
            <div className="recording-continuity">
              <div className="recording-correlation-heading">
                <div>
                  <span className="agent-eyebrow">Collection continuity</span>
                  <h3>Observed collection cycles</h3>
                  <p>
                    Sync confirms delivery; cycle markers show when the Agent collected.
                    Gaps and collector errors can limit conclusions from this recording.
                  </p>
                </div>
                <strong>{analysis.summary.collection_integrity.status}</strong>
              </div>
              <div className="recording-continuity-stats">
                <span>{analysis.summary.collection_integrity.cycle_count} cycles</span>
                <span>
                  Cadence {analysis.summary.collection_integrity.configured_interval_seconds == null
                    ? "—"
                    : `${analysis.summary.collection_integrity.configured_interval_seconds}s`}
                </span>
                <span>{analysis.summary.collection_integrity.collector_error_cycles} error cycles</span>
                <span>
                  {analysis.summary.collection_integrity.status === "unavailable"
                    ? "Gaps unavailable"
                    : `${analysis.summary.collection_integrity.gaps.length} gaps`}
                </span>
              </div>
              {analysis.summary.collection_integrity.gaps.length > 0 && (
                <ul>
                  {analysis.summary.collection_integrity.gaps.map((gap, index) => (
                    <li key={`${gap.started_at}-${index}`}>
                      {formatDate(gap.started_at)} → {formatDate(gap.ended_at)}
                      {" "}({gap.duration_seconds.toFixed(1)}s)
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {analysis.summary.disconnection_intervals && (
            <div className="recording-outages">
              <div className="recording-correlation-heading">
                <div>
                  <span className="agent-eyebrow">Association</span>
                  <h3>Observed disconnection intervals</h3>
                  <p>
                    Durations compare sampled disconnect and reconnect times. Missing
                    boundaries or collection gaps leave the duration unavailable.
                  </p>
                </div>
                <small>
                  {analysis.summary.disconnection_summary?.bounded ?? 0} bounded ·{" "}
                  {analysis.summary.disconnection_summary?.limited ?? 0} limited ·{" "}
                  {analysis.summary.disconnection_summary?.open ?? 0} open
                </small>
              </div>
              {analysis.summary.disconnection_intervals.length === 0 ? (
                <p className="recording-outages-empty">
                  No disconnection intervals in the available state changes.
                </p>
              ) : (
                <div className="recording-outage-list">
                  {analysis.summary.disconnection_intervals.map((interval, index) => (
                    <article key={`${interval.disconnected_at}-${index}`}>
                      <div className="recording-outage-top">
                        <strong>
                          {formatDate(interval.disconnected_at)} →{" "}
                          {interval.reconnected_at
                            ? formatDate(interval.reconnected_at)
                            : "No observed reconnection"}
                        </strong>
                        <span>{interval.status}</span>
                      </div>
                      <p>
                        Sampled interval: {interval.duration_seconds == null
                          ? "unavailable"
                          : `${interval.duration_seconds.toFixed(1)}s`}
                      </p>
                      {interval.limitations.map((reason) => <small key={reason}>{reason}</small>)}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}

          {(analysis.summary.degraded_windows?.length ?? 0) > 0 && (
            <div className="recording-correlation">
              <div className="recording-correlation-heading">
                <div>
                  <span className="agent-eyebrow">Temporal correlation</span>
                  <h3>Correlated degraded windows</h3>
                  <p>
                    Consecutive samples where at least two Wi-Fi evidence domains
                    crossed their configured thresholds at the same time.
                  </p>
                </div>
                <small>
                  {analysis.summary.temporal_correlation?.correlated_samples ?? 0}{" "}
                  correlated samples
                </small>
              </div>
              <div className="recording-window-list">
                {analysis.summary.degraded_windows?.map((window, index) => (
                  <button
                    type="button"
                    key={`${window.started_at}-${index}`}
                    className={[
                      "recording-window",
                      `window-${window.severity}`,
                      selectedWindow?.started_at === window.started_at
                        && selectedWindow?.ended_at === window.ended_at
                        ? "is-selected"
                        : "",
                    ].join(" ")}
                    onClick={() => onSelectWindow(window)}
                  >
                    <div className="recording-window-top">
                      <div>
                        <span>{window.severity}</span>
                        <strong>
                          {formatClock(window.started_at)} →{" "}
                          {formatClock(window.ended_at)}
                        </strong>
                      </div>
                      <small>
                        {window.duration_seconds.toFixed(1)}s ·{" "}
                        {window.sample_count} samples
                      </small>
                    </div>
                    <div className="recording-window-domains">
                      {window.domains.map((domain) => (
                        <span key={domain}>{domain}</span>
                      ))}
                    </div>
                    <dl>
                      <dt>RSSI min</dt>
                      <dd>{metricOrDash(window.minimum_rssi_dbm, " dBm")}</dd>
                      <dt>Retries max</dt>
                      <dd>{metricOrDash(window.maximum_retries_per_100_packets, "/100")}</dd>
                      <dt>TX fail max</dt>
                      <dd>{metricOrDash(window.maximum_tx_failed_percent, "%")}</dd>
                      <dt>Channel util max</dt>
                      <dd>{metricOrDash(window.maximum_channel_utilization_percent, "%")}</dd>
                    </dl>
                  </button>
                ))}
              </div>
            </div>
          )}

          {(analysis.summary.bssid_transitions?.length ?? 0) > 0 && (
            <div className="recording-bssid-comparison">
              <div className="recording-correlation-heading">
                <div>
                  <span className="agent-eyebrow">Association changes</span>
                  <h3>Before and after BSSID changes</h3>
                  <p>
                    Median values within {analysis.summary.bssid_transitions?.[0].comparison_seconds}s
                    on each side. Changes in channel and traffic can affect these measurements;
                    they do not establish why the client changed APs.
                  </p>
                </div>
              </div>
              <div className="recording-bssid-list">
                {analysis.summary.bssid_transitions?.map((transition, index) => (
                  <article className="recording-bssid-card" key={`${transition.observed_at}-${index}`}>
                    <header>
                      <strong>{formatDate(transition.observed_at)}</strong>
                      <span>{transition.status}</span>
                    </header>
                    <p><code>{transition.previous_bssid}</code> → <code>{transition.current_bssid}</code></p>
                    <div className="recording-bssid-table-wrap">
                      <table>
                        <thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
                        <tbody>
                          {BSSID_METRICS.map(({ key, label, unit }) => {
                            const metric = transition.metrics[key];
                            return (
                              <tr key={key}>
                                <th scope="row">{label}</th>
                                <td>{metricOrDash(metric?.before_median ?? null, ` ${unit}`)}</td>
                                <td>{metricOrDash(metric?.after_median ?? null, ` ${unit}`)}</td>
                                <td>{metric?.delta == null ? "—" : `${metric.delta > 0 ? "+" : ""}${metric.delta.toFixed(1)} ${unit}`}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {transition.limitations.map((reason) => <small key={reason}>{reason}</small>)}
                  </article>
                ))}
              </div>
            </div>
          )}

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
