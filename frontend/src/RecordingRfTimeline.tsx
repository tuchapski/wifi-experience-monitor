import { useEffect, useMemo, useState } from "react";

import { getRecordingRfScans, getRecordingRfSummary } from "./agentApi";
import type {
  RecordingRfSummary, RfBssObservation, RfScanSnapshot,
} from "./agentTypes";
import {
  buildRecordingRfTimeline,
  RECORDING_RF_STRONG_NEIGHBOR_DBM,
} from "./recordingRfTimeline";
import { rfBandLabel } from "./rfEnvironment";
import RfDerivedSummary from "./RecordingRfSummary";
import "./RecordingRfTimeline.css";

const DETAIL_ROWS = 120;

function number(value: number | null | undefined, unit = ""): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return unit ? `${rendered} ${unit}` : rendered;
}

function shortBssid(value: string | null | undefined): string {
  if (!value) return "—";
  const parts = value.split(":");
  return parts.length === 6 ? parts.slice(3).join(":") : value;
}

function bssLabel(bss: RfBssObservation | null): string {
  if (!bss) return "No associated BSS observed";
  return `${bss.ssid || "Hidden SSID"} · ${bss.bssid}`;
}

function RecordingRfTimelineContent({
  recordingId,
  active,
  startedAt,
  endedAt,
}: {
  recordingId: string;
  active: boolean;
  startedAt: string | null;
  endedAt: string | null;
}) {
  const [scans, setScans] = useState<RfScanSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<RecordingRfSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [scansLoaded, setScansLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;

    let refreshing = false;
    async function refresh(): Promise<void> {
      if (refreshing) return;
      refreshing = true;
      await Promise.all([
        getRecordingRfScans(recordingId).then((data) => {
          if (mounted) {
            setScans(data);
            setScansLoaded(true);
            setError(null);
          }
        }).catch((err: unknown) => {
          if (mounted) setError(err instanceof Error ? err.message : "Unable to load RF recording evidence");
        }),
        getRecordingRfSummary(recordingId).then((value) => {
          if (mounted) { setSummary(value); setSummaryError(null); }
        }).catch((err: unknown) => {
          if (mounted) {
            setSummary(null);
            setSummaryError(err instanceof Error ? err.message : "Unable to load RF summary");
          }
        }),
      ]);
      refreshing = false;
    }

    void refresh();
    if (!active) {
      return () => {
        mounted = false;
      };
    }

    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [active, recordingId]);

  const data = useMemo(() => buildRecordingRfTimeline(scans), [scans]);
  const chartViews = data.views.filter((view) => view.associated?.rssi_dbm != null);
  const chartStartCandidate = startedAt ? Date.parse(startedAt) : Number.NaN;
  const chartEndCandidate = endedAt ? Date.parse(endedAt) : Number.NaN;
  const firstScanTime = data.views[0] ? Date.parse(data.views[0].scan.observed_at) : Number.NaN;
  const lastView = data.views[data.views.length - 1];
  const lastScanTime = lastView ? Date.parse(lastView.scan.observed_at) : Number.NaN;
  const chartStart = Number.isFinite(chartStartCandidate) ? chartStartCandidate : firstScanTime;
  const chartEndRaw = Number.isFinite(chartEndCandidate) ? chartEndCandidate : lastScanTime;
  const chartEnd = Number.isFinite(chartEndRaw) && chartEndRaw > chartStart
    ? chartEndRaw
    : chartStart + 1;

  let minimumRssi = -90;
  let maximumRssi = -40;
  if (chartViews.length > 0) {
    const readings = chartViews.map((view) => view.associated!.rssi_dbm!);
    minimumRssi = Math.min(...readings) - 4;
    maximumRssi = Math.max(...readings) + 4;
    if (minimumRssi === maximumRssi) {
      minimumRssi -= 1;
      maximumRssi += 1;
    }
  }

  const xForTime = (value: string) => {
    const time = Date.parse(value);
    const ratio = (time - chartStart) / Math.max(1, chartEnd - chartStart);
    return 20 + Math.min(1, Math.max(0, ratio)) * 680;
  };
  const yForRssi = (value: number) => (
    150 - ((value - minimumRssi) / Math.max(1, maximumRssi - minimumRssi)) * 116
  );
  const polyline = chartViews
    .map((view) => `${xForTime(view.scan.observed_at)},${yForRssi(view.associated!.rssi_dbm!)}`)
    .join(" ");
  const recentViews = [...data.views].reverse().slice(0, DETAIL_ROWS);

  return (
    <section className="agent-panel recording-rf-timeline">
      <div className="recording-detail-section-heading">
        <div>
          <span className="agent-eyebrow">RF environment timeline</span>
          <h2>BSS neighborhood across the recording</h2>
          <p>
            Active-scan evidence captured from this client position while the diagnostic
            recording was active.
          </p>
        </div>
        <small>{summary ? `${summary.scan_count.toLocaleString()} stored RF scans` : "RF evidence"}</small>
      </div>

      {summaryError ? <div className="recording-rf-empty">RF summary: {summaryError}</div>
        : summary ? (summary.scan_count > 0 ? <RfDerivedSummary summary={summary} /> : null)
        : <div className="recording-rf-empty">Loading RF summary…</div>}

      {error ? (
        <div className="recording-rf-empty">{error}</div>
      ) : !scansLoaded ? (
        <div className="recording-rf-empty">Loading RF scan evidence…</div>
      ) : data.summary.scanCount === 0 ? (
        <div className="recording-rf-empty">
          No RF scans were associated with this recording.
        </div>
      ) : (
        <>
          <p className="recording-rf-note">
            Timeline and snapshot statistics below cover the latest {data.summary.scanCount} scans
            (up to 2,000). {summary && "The summary above covers all stored scans."}
          </p>
          <div className="recording-rf-summary">
            <article>
              <span>RF scans</span>
              <strong>{data.summary.scanCount}</strong>
            </article>
            <article>
              <span>BSS observations</span>
              <strong>{data.summary.totalBssObservations}</strong>
            </article>
            <article>
              <span>Unique BSS</span>
              <strong>{data.summary.uniqueBss}</strong>
            </article>
            <article>
              <span>Associated BSSID changes</span>
              <strong>{data.summary.associatedBssidChanges}</strong>
            </article>
            <article>
              <span>Association visible</span>
              <strong>{data.summary.associationCoveragePercent.toFixed(0)}%</strong>
            </article>
          </div>

          <article className="recording-rf-chart">
            <header>
              <div>
                <span>Associated BSS signal</span>
                <strong>RSSI across RF scans</strong>
              </div>
              <small>
                {chartViews.length}/{data.summary.scanCount} scans with associated RSSI
              </small>
            </header>

            {chartViews.length === 0 ? (
              <div className="recording-rf-chart-empty">Associated RSSI was unavailable.</div>
            ) : (
              <>
                <svg viewBox="0 0 720 178" role="img" aria-label="Associated BSS RSSI over recording">
                  <line x1="20" x2="700" y1="34" y2="34" className="recording-rf-gridline" />
                  <line x1="20" x2="700" y1="92" y2="92" className="recording-rf-gridline" />
                  <line x1="20" x2="700" y1="150" y2="150" className="recording-rf-gridline" />
                  {data.views.filter((view) => view.associatedChanged).map((view) => (
                    <line
                      key={`transition-${view.scan.scan_id}`}
                      x1={xForTime(view.scan.observed_at)}
                      x2={xForTime(view.scan.observed_at)}
                      y1="28"
                      y2="154"
                      className="recording-rf-transition-line"
                    >
                      <title>
                        Associated BSSID changed at {new Date(view.scan.observed_at).toLocaleString()}
                      </title>
                    </line>
                  ))}
                  <polyline points={polyline} className="recording-rf-line" />
                  {chartViews.map((view) => (
                    <circle
                      key={view.scan.scan_id}
                      cx={xForTime(view.scan.observed_at)}
                      cy={yForRssi(view.associated!.rssi_dbm!)}
                      r={view.associatedChanged ? 4 : 2.5}
                      className={view.associatedChanged
                        ? "recording-rf-point is-transition"
                        : "recording-rf-point"}
                    >
                      <title>
                        {new Date(view.scan.observed_at).toLocaleString()} ·{" "}
                        {bssLabel(view.associated)} · {number(view.associated!.rssi_dbm, "dBm")}
                      </title>
                    </circle>
                  ))}
                </svg>
                <div className="recording-rf-axis">
                  <span>
                    {Number.isFinite(chartStart) ? new Date(chartStart).toLocaleTimeString() : "—"}
                  </span>
                  <span>
                    {Number.isFinite(chartEnd) ? new Date(chartEnd).toLocaleTimeString() : "—"}
                  </span>
                </div>
              </>
            )}
          </article>

          <details className="recording-rf-snapshots">
            <summary>
              RF scan snapshots · showing {Math.min(DETAIL_ROWS, data.views.length)} of{" "}
              {data.views.length}
            </summary>
            <div className="recording-rf-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Associated BSS</th>
                    <th>Band / channel</th>
                    <th>RSSI</th>
                    <th>Visible BSS</th>
                    <th>Same SSID</th>
                    <th>Strong neighbors</th>
                    <th>Best same-SSID alternative</th>
                  </tr>
                </thead>
                <tbody>
                  {recentViews.map((view) => {
                    const associated = view.associated;
                    const alternative = view.bestSameSsidAlternative;
                    return (
                      <tr key={view.scan.scan_id}>
                        <td>
                          <time title={new Date(view.scan.observed_at).toLocaleString()}>
                            {new Date(view.scan.observed_at).toLocaleTimeString()}
                          </time>
                        </td>
                        <td>
                          <strong>{associated?.ssid || "Unavailable"}</strong>
                          <code title={associated?.bssid ?? undefined}>
                            {shortBssid(associated?.bssid)}
                          </code>
                          {view.associatedChanged && <em>BSSID changed</em>}
                        </td>
                        <td>
                          {associated
                            ? `${rfBandLabel(associated.band)} · Ch ${associated.channel ?? "—"}`
                            : "—"}
                        </td>
                        <td>{number(associated?.rssi_dbm, "dBm")}</td>
                        <td>{view.scan.bsses.length}</td>
                        <td>{view.sameSsid}</td>
                        <td>
                          {view.strongNeighbors}
                          <small> ≥ {RECORDING_RF_STRONG_NEIGHBOR_DBM} dBm</small>
                        </td>
                        <td>
                          {alternative ? (
                            <>
                              <strong>{alternative.ssid || "Hidden SSID"}</strong>
                              <code title={alternative.bssid}>{shortBssid(alternative.bssid)}</code>
                              <small>
                                {number(alternative.rssi_dbm, "dBm")} · Δ{" "}
                                {number(view.alternativeDeltaDb, "dB")}
                              </small>
                            </>
                          ) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </details>

          <p className="recording-rf-note">
            BSSID changes, neighbor counts, channels and signal levels are client-side active-scan
            observations. They do not measure airtime utilization or non-Wi-Fi interference and do
            not establish why the client selected or changed an AP.
          </p>
        </>
      )}
    </section>
  );
}

export default function RecordingRfTimeline(
  props: Parameters<typeof RecordingRfTimelineContent>[0],
) {
  return <RecordingRfTimelineContent key={props.recordingId} {...props} />;
}
