import { useEffect, useState } from "react";

import SensorControl from "./SensorControl";
import WifiDetails from "./WifiDetails";
import HistoryPanel from "./HistoryPanel";

import {
  clearIncidentHistory,
  getActiveIncidents,
  getIncidentHistory,
  getLatestSnapshot,
} from "./api";

import type {
  IncidentRecord,
  SensorSnapshot,
  SensorStatus,
  TestOutcome,
} from "./types";

import "./App.css";


function formatNumber(
  value: number | null,
  suffix = "",
): string {
  if (value == null || !Number.isFinite(value)) {
    return "Unavailable";
  }

  return `${value}${suffix}`;
}


function formatStatus(
  value: string | null,
): string {
  if (value === null) {
    return "UNKNOWN";
  }

  return value.toUpperCase();
}


function formatDate(
  value: string | null,
): string {
  if (value === null) {
    return "—";
  }

  return new Date(value).toLocaleString();
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "Unavailable";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)} s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${remainder}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function incidentColor(severity: string): string {
  if (severity === "critical") return "#b42318";
  if (severity === "warning") return "#d97706";
  return "#175cd3";
}

function IncidentTimeline({ incidents }: { incidents: IncidentRecord[] }) {
  if (incidents.length === 0) {
    return null;
  }

  const now = Date.now();
  const timestamps = incidents.flatMap((incident) => [
    new Date(incident.started_at).getTime(),
    incident.ended_at ? new Date(incident.ended_at).getTime() : now,
  ]);
  const start = Math.min(...timestamps);
  const end = Math.max(...timestamps);
  const span = Math.max(1, end - start);
  const left = 220;
  const right = 20;
  const width = 960;
  const chartWidth = width - left - right;
  const rowHeight = 38;
  const top = 34;
  const height = top + incidents.length * rowHeight + 32;
  const x = (timestamp: number) => left + ((timestamp - start) / span) * chartWidth;

  return (
    <section className="incident-timeline panel" aria-labelledby="incident-timeline-title">
      <h2 id="incident-timeline-title">Incident timeline</h2>
      <p className="metric-note">
        Each bar represents one incident interval. Open intervals extend to the current time.
      </p>
      <div className="incident-timeline-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Incident duration timeline">
          {[0, 0.5, 1].map((fraction) => {
            const timestamp = start + span * fraction;
            return (
              <g key={fraction}>
                <line x1={x(timestamp)} x2={x(timestamp)} y1="20" y2={height - 24} stroke="#e4e7ec" />
                <text x={x(timestamp)} y="14" textAnchor={fraction === 0 ? "start" : fraction === 1 ? "end" : "middle"}>
                  {new Date(timestamp).toLocaleString()}
                </text>
              </g>
            );
          })}
          {incidents.map((incident, index) => {
            const incidentStart = new Date(incident.started_at).getTime();
            const incidentEnd = incident.ended_at ? new Date(incident.ended_at).getTime() : now;
            const barWidth = Math.max(5, x(incidentEnd) - x(incidentStart));
            const y = top + index * rowHeight;
            return (
              <g key={incident.id}>
                <text x="8" y={y + 16} dominantBaseline="middle">{incident.code}</text>
                <rect x={x(incidentStart)} y={y} width={barWidth} height="20" rx="4" fill={incidentColor(incident.severity)}>
                  <title>{`${incident.code}: ${formatDuration(incident.duration_seconds)} · ${incident.message}`}</title>
                </rect>
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}


function TestDetails({ outcome }: { outcome?: TestOutcome }) {
  const labels: Record<string, string> = {
    passed: "Passed", failed: "Failed", error: "Collection error",
    skipped: "Not run", unavailable: "Unavailable", observed: "Observed",
  };
  return <small>
    <strong>{outcome ? labels[outcome.status] ?? outcome.status : "Unavailable"}</strong>
    {outcome && <><br />{outcome.reason}<br />
      {outcome.scope === "host" ? "Host route (not bound to selected Wi-Fi)" : "Selected interface"}
    </>}
  </small>;
}

function App() {
  const [sensorStatus, setSensorStatus] = useState<SensorStatus | null>(null);
  const [snapshot, setSnapshot] =
    useState<SensorSnapshot | null>(null);


  const [
    activeIncidents,
    setActiveIncidents,
  ] = useState<IncidentRecord[]>([]);

  const [
    incidentHistory,
    setIncidentHistory,
  ] = useState<IncidentRecord[]>([]);

  const [clearingHistory, setClearingHistory] = useState(false);

  const [error, setError] =
    useState<string | null>(null);


  async function refresh() {
    try {
      const [
        latestData,
        activeIncidentData,
        incidentHistoryData,
      ] = await Promise.all([
        getLatestSnapshot(),
        getActiveIncidents(),
        getIncidentHistory(50),
      ]);

      setSnapshot(latestData);


      setActiveIncidents(
        activeIncidentData,
      );

      setIncidentHistory(
        incidentHistoryData,
      );

      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unknown error",
      );
    }
  }

  async function clearHistory() {
    if (incidentHistory.length === 0 || !window.confirm(
      "Clear ended incidents from Incident History? Currently open incidents will be preserved.",
    )) {
      return;
    }
    setClearingHistory(true);
    try {
      await clearIncidentHistory();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to clear incident history.");
    } finally {
      setClearingHistory(false);
    }
  }


  useEffect(() => {
    void refresh();

    const timer = window.setInterval(
      () => {
        void refresh();
      },
      5000,
    );

    return () => {
      window.clearInterval(timer);
    };
  }, []);


  const currentSnapshot = sensorStatus?.running && sensorStatus.started_at && snapshot
    && snapshot.wifi.interface === sensorStatus.interface
    && Date.parse(snapshot.timestamp) >= Date.parse(sensorStatus.started_at);

  if (!currentSnapshot || snapshot === null) {
    return (
      <main className="page">

        <header className="header">

          <div>
            <h1>
              Wi-Fi Experience Monitor
            </h1>

            <p>
              Configure the monitoring sensor.
            </p>
          </div>

        </header>


        <SensorControl onStatusChange={setSensorStatus} />


        {error !== null && (
          <div className="error">
            {error}
          </div>
        )}


        <div className="empty-state">
          {sensorStatus?.running
            ? "Waiting for the first sample of this monitoring session."
            : "Monitoring stopped. Select a valid Wi-Fi interface and click Start Monitoring."}

        </div>
        <HistoryPanel currentInterface={sensorStatus?.interface} />

      </main>
    );
  }


  return (
    <main className="page">

      <header className="header">

        <div>

          <h1>
            Wi-Fi Experience Monitor
          </h1>

          <p>
            {snapshot.wifi.ssid ?? "Unknown SSID"}
            {" · "}
            {snapshot.wifi.interface}
          </p>

        </div>


        <div className="timestamp">
          {new Date(
            snapshot.timestamp,
          ).toLocaleString()}
        </div>

      </header>


      <SensorControl onStatusChange={setSensorStatus} />


      {error !== null && (
        <div className="error">
          {error}
        </div>
      )}


      {snapshot.diagnostic?.complete === false && (
        <div className="empty-state">
          Assessment incomplete: missing measurements or unresolved sensor checks.
          Available findings are shown below; missing data is not evidence of recovery.
        </div>
      )}

      <section className="diagnostic-overview">

        <div>

          <span>
            Overall Experience
          </span>

          <strong
            className={
              snapshot.diagnostic
                ? `status-${snapshot.diagnostic.overall_status}`
                : ""
            }
          >
            {snapshot.diagnostic
              ? formatStatus(
                  snapshot.diagnostic.overall_status,
                )
              : "UNKNOWN"}
          </strong>

        </div>


        <div>

          <span>
            Probable Domain
          </span>

          <strong>
            {snapshot.diagnostic
              ?.probable_domain ?? "None"}
          </strong>

        </div>


        <div>

          <span>
            Active Incidents
          </span>

          <strong
            className={
              activeIncidents.length > 0
                ? "status-critical"
                : "status-healthy"
            }
          >
            {activeIncidents.length}
          </strong>

        </div>

      </section>


      <section className="cards">

        <div className="card">

          <span>
            RSSI
          </span>

          <strong>
            {formatNumber(
              snapshot.wifi.signal_dbm,
              " dBm",
            )}
          </strong>

        </div>


        <div className="card">

          <span>
            Gateway
          </span>

          <strong>
            {formatNumber(
              snapshot.connectivity
                .gateway_latency_avg_ms,
              " ms",
            )}
          </strong>

          <TestDetails outcome={snapshot.connectivity.tests?.gateway} />

        </div>


        <div className="card">

          <span>
            Internet
          </span>

          <strong>
            {formatNumber(
              snapshot.connectivity
                .internet_latency_avg_ms,
              " ms",
            )}
          </strong>

          <TestDetails outcome={snapshot.connectivity.tests?.internet} />

        </div>


        <div className="card">

          <span>
            DNS
          </span>

          <strong>
            {formatNumber(
              snapshot.connectivity
                .dns_latency_ms,
              " ms",
            )}
          </strong>

          <TestDetails outcome={snapshot.connectivity.tests?.dns} />

        </div>


        <div className="card">

          <span>
            HTTPS
          </span>

          <strong>
            {formatNumber(
              snapshot.connectivity
                .https_total_time_ms,
              " ms",
            )}
          </strong>

          <TestDetails outcome={snapshot.connectivity.tests?.https} />

        </div>


        <div className="card">

          <span>
            TX Retries
          </span>

          <strong>
            {formatNumber(
              snapshot.wifi_delta
                ?.tx_retries_per_100_packets
                ?? null,
            )}
          </strong>

        </div>

      </section>


      <section className="details">

        <div className="panel">

          <h2>
            Wi-Fi
          </h2>

          <dl>

            <dt>
              Interface
            </dt>

            <dd>
              {snapshot.wifi.interface}
            </dd>


            <dt>
              SSID
            </dt>

            <dd>
              {snapshot.wifi.ssid ?? "N/A"}
            </dd>


            <dt>
              BSSID
            </dt>

            <dd>
              {snapshot.wifi.bssid ?? "N/A"}
            </dd>


            <dt>
              Channel
            </dt>

            <dd>
              {snapshot.wifi.channel ?? "N/A"}
            </dd>


            <dt>
              Signal
            </dt>

            <dd>
              {formatNumber(
                snapshot.wifi.signal_dbm,
                " dBm",
              )}
            </dd>

          </dl>

        </div>


        <div className="panel">

          <h2>
            Network
          </h2>

          <dl>

            <dt>
              IPv4
            </dt>

            <dd>
              {snapshot.network
                .ipv4_address ?? "N/A"}
            </dd>


            <dt>
              Gateway
            </dt>

            <dd>
              {snapshot.network
                .gateway ?? "N/A"}
            </dd>


            <dt>
              DNS
            </dt>

            <dd>
              {snapshot.network
                .dns_servers.length > 0
                ? snapshot.network
                    .dns_servers.join(", ")
                : "N/A"}
            </dd>

          </dl>

        </div>

      </section>


      <WifiDetails snapshot={snapshot} />

      {activeIncidents.length > 0 && (
        <section className="active-incidents">

          <h2>
            Active Incidents
          </h2>

          <div className="incident-grid">

            {activeIncidents.map(
              (incident) => (

                <article
                  key={incident.id}
                  className={
                    `incident-card incident-${incident.severity}`
                  }
                >

                  <strong>
                    {incident.code}
                  </strong>

                  <p>
                    {incident.message}
                  </p>

                  <small>
                    {incident.domain}
                    {" · "}
                    {incident.severity}
                  </small>

                </article>

              ),
            )}

          </div>

        </section>
      )}


      <section className="incident-history">

        <div className="incident-history-heading">
          <h2>Incident History</h2>
          <button type="button" onClick={() => void clearHistory()} disabled={clearingHistory || incidentHistory.length === 0}>
            {clearingHistory ? "Clearing…" : "Clear history"}
          </button>
        </div>

        {incidentHistory.length === 0 ? (

          <div className="empty-state">
            No incidents recorded.
          </div>

        ) : (

          <div className="table-wrapper">

            <table>

              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Domain</th>
                  <th>Code</th>
                  <th>Started</th>
                  <th>Ended</th>
                  <th>Duration</th>
                </tr>
              </thead>

              <tbody>

                {incidentHistory.map(
                  (incident) => (

                    <tr key={incident.id}>

                      <td>
                        {incident.severity}
                      </td>

                      <td>
                        {incident.domain}
                      </td>

                      <td>
                        {incident.code}
                      </td>

                      <td>
                        {formatDate(
                          incident.started_at,
                        )}
                      </td>

                      <td>{incident.is_open ? "Ongoing" : formatDate(incident.ended_at)}</td>

                      <td>{formatDuration(incident.duration_seconds)}</td>

                    </tr>

                  ),
                )}

              </tbody>

            </table>

          </div>

        )}

      </section>

      <IncidentTimeline incidents={incidentHistory} />


      {snapshot.diagnostic && snapshot.diagnostic.findings.length > 0 && (
        <section className="panel">
          <h2>Diagnostic evidence</h2>
          <ul>{snapshot.diagnostic.findings.map((finding) => (
            <li key={finding.code}>
              <strong>{finding.severity.toUpperCase()} · {finding.domain}</strong>
              {" — "}{finding.message}
            </li>
          ))}</ul>
        </section>
      )}

      {snapshot.recommendations && snapshot.recommendations.length > 0 && (
        <section className="panel recommendations-panel">
          <h2>Recommended actions</h2>
          <p className="metric-note">Recommendations are evidence-based suggestions, not proof of root cause.</p>
          <div className="recommendation-grid">
            {snapshot.recommendations.map((item) => (
              <article key={item.code} className={`recommendation-card recommendation-${item.severity}`}>
                <span>{item.severity.toUpperCase()}</span>
                <h3>{item.title}</h3>
                <p><strong>Action:</strong> {item.action}</p>
                <p><strong>Why:</strong> {item.rationale}</p>
                <small><strong>Evidence:</strong> {item.evidence}</small>
              </article>
            ))}
          </div>
        </section>
      )}

      {snapshot.calibration && (
        <section className="panel">

          <h2>
            Sensor Calibration
          </h2>

          <p>
            Status:{" "}
            <strong>
              {snapshot.calibration.status}
            </strong>
          </p>

          <p>
            Calibrated:{" "}
            <strong>
              {snapshot.calibration.calibrated
                ? "Yes"
                : "No"}
            </strong>
          </p>
          <p>These checks describe what the sensor could verify. They do not rule out every local cause.</p>
          <div className="table-wrapper">
            <table>
              <thead><tr><th>Check</th><th>Result</th><th>Evidence</th></tr></thead>
              <tbody>{Object.entries(snapshot.calibration.checks ?? {}).map(([name, check]) => (
                <tr key={name}>
                  <td>{name.replaceAll("_", " ")}</td>
                  <td>{check.status === "unavailable" ? "Inconclusive" : "Observed"}</td>
                  <td>{check.reason}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <ul>{snapshot.calibration.findings.map((finding) => (
            <li key={finding.code}><strong>{finding.severity.toUpperCase()}</strong>{" — "}{finding.message}</li>
          ))}</ul>


        </section>
      )}


      {snapshot.collector_errors.length > 0 && (
        <section className="errors-panel">

          <h2>
            Sensor Errors
          </h2>

          <ul>

            {snapshot.collector_errors.map(
              (item) => (

                <li key={item}>
                  {item}
                </li>

              ),
            )}

          </ul>

        </section>
      )}


      <HistoryPanel currentInterface={sensorStatus?.interface} />

    </main>
  );
}


export default App;
