import { useEffect, useMemo, useState } from "react";

import { getLatestRfScan } from "./agentApi";
import type { RfBssObservation, RfScanSnapshot, WifiCurrentState } from "./agentTypes";
import {
  rfBandLabel,
  STRONG_NEIGHBOR_RSSI_DBM,
  summarizeRfEnvironment,
} from "./rfEnvironment";
import "./RfEnvironmentPanel.css";

function metric(value: number | null | undefined, unit = ""): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return unit ? `${formatted} ${unit}` : formatted;
}

function bssDescription(bss: RfBssObservation | null): string {
  if (!bss) return "Unavailable";
  return `${rfBandLabel(bss.band)} · Ch ${bss.channel ?? "—"} · ${metric(bss.rssi_dbm, "dBm")}`;
}

export default function RfEnvironmentPanel({
  agentId,
  wifi,
}: {
  agentId: string;
  wifi: WifiCurrentState | null | undefined;
}) {
  const [scan, setScan] = useState<RfScanSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function refresh(): Promise<void> {
      try {
        const latest = await getLatestRfScan(agentId);
        if (active) {
          setScan(latest);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load RF environment");
        }
      }
    }

    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [agentId]);

  const summary = useMemo(
    () => (scan ? summarizeRfEnvironment(scan, wifi) : null),
    [scan, wifi],
  );

  return (
    <section className="agent-panel rf-environment-panel">
      <div className="agent-panel-heading">
        <div>
          <span className="agent-eyebrow">RF neighborhood</span>
          <h2>RF Environment</h2>
          <p>Active-scan observations from this client position.</p>
        </div>
        <small>
          {scan
            ? `${new Date(scan.observed_at).toLocaleTimeString()} · ${scan.duration_ms.toFixed(0)} ms`
            : "Waiting for scan"}
        </small>
      </div>

      {error ? (
        <div className="rf-environment-empty">{error}</div>
      ) : !scan || !summary ? (
        <div className="rf-environment-empty">No RF neighborhood scan is available yet.</div>
      ) : (
        <>
          <div className="rf-environment-stats">
            <article><span>Visible BSS</span><strong>{summary.visibleBss}</strong></article>
            <article><span>Visible SSIDs</span><strong>{summary.visibleSsids}</strong></article>
            <article><span>Same SSID</span><strong>{summary.sameSsid}</strong></article>
            <article><span>Same channel</span><strong>{summary.sameChannel}</strong></article>
            <article>
              <span>Strong neighbors</span>
              <strong>{summary.strongNeighbors}</strong>
              <small>≥ {STRONG_NEIGHBOR_RSSI_DBM} dBm</small>
            </article>
          </div>

          <div className="rf-environment-focus">
            <article>
              <span>Associated BSS</span>
              <strong>{summary.associated?.ssid || "Hidden / unknown SSID"}</strong>
              <code>{summary.associated?.bssid ?? wifi?.bssid ?? "—"}</code>
              <small>{bssDescription(summary.associated)}</small>
            </article>
            <article>
              <span>Best same-SSID alternative</span>
              <strong>{summary.bestSameSsidAlternative?.ssid ?? "No alternative observed"}</strong>
              <code>{summary.bestSameSsidAlternative?.bssid ?? "—"}</code>
              <small>
                {summary.bestSameSsidAlternative
                  ? `${bssDescription(summary.bestSameSsidAlternative)} · Δ ${metric(summary.alternativeDeltaDb, "dB")}`
                  : "No other BSS for the associated SSID in this scan"}
              </small>
            </article>
          </div>

          <details className="rf-environment-inventory">
            <summary>BSS inventory · {scan.bsses.length} observations</summary>
            <div className="rf-environment-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>SSID / BSSID</th><th>Band</th><th>Channel</th>
                    <th>RSSI</th><th>Width</th><th>PHY capabilities</th>
                  </tr>
                </thead>
                <tbody>
                  {scan.bsses.map((bss) => (
                    <tr key={bss.bssid} className={bss.associated ? "associated" : ""}>
                      <td>
                        <strong>{bss.ssid || "Hidden SSID"}</strong>
                        <code>{bss.bssid}</code>
                      </td>
                      <td>{rfBandLabel(bss.band)}</td>
                      <td>{bss.channel ?? "—"}</td>
                      <td>{metric(bss.rssi_dbm, "dBm")}</td>
                      <td>{metric(bss.channel_width_mhz, "MHz")}</td>
                      <td>{bss.phy_capabilities.join(" / ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <p className="rf-environment-note">
            BSS counts and signal levels do not measure airtime utilization,
            non-Wi-Fi interference or congestion, and do not explain why the client
            selected or changed an AP.
          </p>
        </>
      )}
    </section>
  );
}
