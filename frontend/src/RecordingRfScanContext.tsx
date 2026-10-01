import type { RecordingRfScanWindows } from "./agentTypes";

export default function RecordingRfScanContext({ data, error, enabled, onToggle }: {
  data: RecordingRfScanWindows | null;
  error: string | null;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  return <section className="agent-panel recording-rf-context" aria-label="RF scan context">
    <label>
      <input type="checkbox" checked={enabled} onChange={(event) => onToggle(event.target.checked)} />
      <strong>Show estimated RF scan windows</strong>
      <i className="legend-window legend-rf-scan" aria-hidden="true" />
    </label>
    {error ? <p role="status">RF scan context unavailable: {error}</p>
      : data === null ? <p role="status">Loading RF scan windows…</p>
      : <>
        <p>{data.windows.length.toLocaleString()} valid windows from {data.loaded_scans.toLocaleString()} loaded / {data.total_scans.toLocaleString()} stored scans.</p>
        {data.truncated && <p className="recording-rf-coverage">Partial coverage: only the latest {data.loaded_scans.toLocaleString()} stored scans are shown. Earlier periods have no scan overlay.</p>}
        {data.invalid_windows > 0 && <p>{data.invalid_windows.toLocaleString()} loaded scans have invalid timing and are omitted.</p>}
        {data.total_scans === 0 && <p>No successful RF scans are stored for this recording.</p>}
      </>}
    <p>Estimated from scan completion and duration; only stored successful scans appear. Temporal context, not causal diagnosis. Short windows use a minimum marker width.</p>
  </section>;
}
