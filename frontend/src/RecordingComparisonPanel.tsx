import { useEffect, useMemo, useState } from "react";

import { getLatestRecordingAnalysis } from "./agentApi";
import type { DiagnosticRecording, RecordingAnalysis } from "./agentTypes";
import "./RecordingComparisonPanel.css";

type Comparison = {
  beforeId: string;
  afterId: string;
  before: RecordingAnalysis | null;
  after: RecordingAnalysis | null;
};

function durationMinutes(recording: DiagnosticRecording): number | null {
  if (!recording.started_at || !recording.ended_at) return null;
  const minutes = (Date.parse(recording.ended_at) - Date.parse(recording.started_at)) / 60000;
  return Number.isFinite(minutes) && minutes >= 0 ? minutes : null;
}

function formatNumber(value: number | null | undefined, unit: string): string {
  return value == null || !Number.isFinite(value) ? "—" : `${value.toFixed(1)}${unit}`;
}

function formatDelta(before: number | null | undefined, after: number | null | undefined, unit: string): string {
  if (before == null || after == null || !Number.isFinite(before) || !Number.isFinite(after)) {
    return "—";
  }
  const delta = after - before;
  return `${delta > 0 ? "+" : ""}${delta.toFixed(1)}${unit}`;
}

function openRecording(agentId: string, recordingId: string): void {
  window.location.hash = `#agents/${encodeURIComponent(agentId)}/recordings/${encodeURIComponent(recordingId)}`;
}

export default function RecordingComparisonPanel({
  agentId,
  recordings,
}: {
  agentId: string;
  recordings: DiagnosticRecording[];
}) {
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eligible = useMemo(
    () => recordings.filter((recording) => recording.status === "completed" && recording.sync_status === "complete"),
    [recordings],
  );
  const beforeRecording = eligible.find((recording) => recording.id === beforeId);
  const afterRecording = eligible.find((recording) => recording.id === afterId);
  const validSelection = Boolean(beforeRecording && afterRecording && beforeId !== afterId);

  useEffect(() => {
    let active = true;
    if (!validSelection) return () => { active = false; };

    async function load(): Promise<void> {
      try {
        const [before, after] = await Promise.all([
          getLatestRecordingAnalysis(beforeId),
          getLatestRecordingAnalysis(afterId),
        ]);
        if (active) {
          setComparison({ beforeId, afterId, before, after });
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load analyses");
          setLoading(false);
        }
      }
    }

    setLoading(true);
    void load();
    return () => { active = false; };
  }, [beforeId, afterId, validSelection]);

  if (eligible.length < 2) return null;

  const result = validSelection && !loading && comparison?.beforeId === beforeId && comparison.afterId === afterId
    ? comparison : null;
  const before = result?.before;
  const after = result?.after;
  const matchingEngines = Boolean(before && after && before.engine_version === after.engine_version);
  const beforeDuration = beforeRecording ? durationMinutes(beforeRecording) : null;
  const afterDuration = afterRecording ? durationMinutes(afterRecording) : null;
  const limitations: string[] = [];

  if (before && after && beforeRecording && afterRecording) {
    if (before.engine_version !== after.engine_version) limitations.push("Analysis engine versions differ.");
    if (beforeRecording.profile_id !== afterRecording.profile_id) limitations.push("Collection profiles differ.");
    if (beforeRecording.site !== afterRecording.site || beforeRecording.location !== afterRecording.location) {
      limitations.push("Site or location differs.");
    }
    if (beforeDuration != null && afterDuration != null
      && Math.max(beforeDuration, afterDuration) > 1.2 * Math.min(beforeDuration, afterDuration)) {
      limitations.push("Recording durations differ by more than 20%.");
    }
    if (before.summary.evidence_status !== "complete" || after.summary.evidence_status !== "complete") {
      limitations.push("At least one analysis has partial evidence.");
    }
    if (before.summary.collection_integrity?.status !== "continuous"
      || after.summary.collection_integrity?.status !== "continuous") {
      limitations.push("Collection continuity is not confirmed for both recordings.");
    }
  }

  const rows = before && after ? [
    { label: "RSSI average", first: before.summary.rssi?.average, second: after.summary.rssi?.average, unit: " dBm" },
    { label: "TX retries P90", first: before.summary.tx_retries_per_100_packets?.p90, second: after.summary.tx_retries_per_100_packets?.p90, unit: "/100" },
    { label: "TX failures P90", first: before.summary.tx_failed_percent?.p90, second: after.summary.tx_failed_percent?.p90, unit: "%" },
    { label: "Channel utilization P90", first: before.summary.channel_utilization_percent?.p90, second: after.summary.channel_utilization_percent?.p90, unit: "%" },
  ] : [];

  return (
    <section className="recording-comparison" aria-labelledby="recording-comparison-title">
      <div className="recording-comparison-heading">
        <h3 id="recording-comparison-title">Compare recordings</h3>
        <p>Choose two completed, synchronized recordings from this Agent.</p>
      </div>
      <div className="recording-comparison-selectors">
        <label htmlFor="recording-before">Before
          <select id="recording-before" value={beforeId} onChange={(event) => {
            setBeforeId(event.target.value);
            setComparison(null);
            setError(null);
          }}>
            <option value="">Select a recording</option>
            {eligible.map((recording) => (
              <option key={recording.id} value={recording.id}>
                {recording.name} · {new Date(recording.started_at ?? recording.created_at).toLocaleString()}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="recording-after">After
          <select id="recording-after" value={afterId} onChange={(event) => {
            setAfterId(event.target.value);
            setComparison(null);
            setError(null);
          }}>
            <option value="">Select a recording</option>
            {eligible.map((recording) => (
              <option key={recording.id} value={recording.id}>
                {recording.name} · {new Date(recording.started_at ?? recording.created_at).toLocaleString()}
              </option>
            ))}
          </select>
        </label>
      </div>
      {beforeId && beforeId === afterId && <p className="recording-comparison-message">Choose two different recordings.</p>}
      {error && validSelection && <p className="recording-comparison-error" role="alert">{error}</p>}
      {loading && validSelection && <p className="recording-comparison-message">Loading analyses…</p>}
      {result && (!before || !after) && (
        <div className="recording-comparison-message">
          <p>Run an analysis for each recording before comparing them.</p>
          {!before && beforeRecording && <button type="button" onClick={() => openRecording(agentId, beforeId)}>Open “before” recording</button>}
          {!after && afterRecording && <button type="button" onClick={() => openRecording(agentId, afterId)}>Open “after” recording</button>}
        </div>
      )}
      {result && before && after && beforeRecording && afterRecording && (
        <>
          <div className="recording-comparison-table-wrap">
            <table className="recording-comparison-table">
              <thead><tr><th scope="col">Measure</th><th scope="col">Before</th><th scope="col">After</th><th scope="col">Change (after − before)</th></tr></thead>
              <tbody>
                <tr><th scope="row">Recording</th><td>{beforeRecording.name}</td><td>{afterRecording.name}</td><td>—</td></tr>
                <tr><th scope="row">Site / location</th><td>{[beforeRecording.site, beforeRecording.location].filter(Boolean).join(" / ") || "—"}</td><td>{[afterRecording.site, afterRecording.location].filter(Boolean).join(" / ") || "—"}</td><td>—</td></tr>
                <tr><th scope="row">Duration</th><td>{formatNumber(beforeDuration, " min")}</td><td>{formatNumber(afterDuration, " min")}</td><td>—</td></tr>
                <tr><th scope="row">Metric samples</th><td>{before.source_metrics_count.toLocaleString()}</td><td>{after.source_metrics_count.toLocaleString()}</td><td>—</td></tr>
                <tr><th scope="row">Evidence</th><td>{before.summary.evidence_status}</td><td>{after.summary.evidence_status}</td><td>—</td></tr>
                <tr><th scope="row">Collection</th><td>{before.summary.collection_integrity?.status ?? "unknown"}</td><td>{after.summary.collection_integrity?.status ?? "unknown"}</td><td>—</td></tr>
                {rows.map(({ label, first, second, unit }) => (
                  <tr key={label}><th scope="row">{label}</th><td>{formatNumber(first, unit)}</td><td>{formatNumber(second, unit)}</td><td>{matchingEngines ? formatDelta(first, second, unit) : "—"}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="recording-comparison-context">
            <p>Analysis engines: {before.engine_version} / {after.engine_version}. Changes require measurements in both recordings and matching engine versions.</p>
            {limitations.length > 0 && <ul>{limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
            <p>Changes are descriptive. Different conditions, durations and gaps can affect measurements; this comparison does not establish a cause.</p>
          </div>
        </>
      )}
    </section>
  );
}
