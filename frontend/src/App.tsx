import { useEffect, useState } from "react";

import SensorControl from "./SensorControl";

import {
  getActiveIncidents,
  getHistory,
  getIncidentHistory,
  getLatestSnapshot,
} from "./api";

import type {
  HistoryRecord,
  IncidentRecord,
  SensorSnapshot,
} from "./types";

import "./App.css";


function formatNumber(
  value: number | null,
  suffix = "",
): string {
  if (value === null) {
    return "N/A";
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


function App() {
  const [snapshot, setSnapshot] =
    useState<SensorSnapshot | null>(null);

  const [history, setHistory] =
    useState<HistoryRecord[]>([]);

  const [
    activeIncidents,
    setActiveIncidents,
  ] = useState<IncidentRecord[]>([]);

  const [
    incidentHistory,
    setIncidentHistory,
  ] = useState<IncidentRecord[]>([]);

  const [error, setError] =
    useState<string | null>(null);


  async function refresh() {
    try {
      const [
        latestData,
        historyData,
        activeIncidentData,
        incidentHistoryData,
      ] = await Promise.all([
        getLatestSnapshot(),
        getHistory(100),
        getActiveIncidents(),
        getIncidentHistory(50),
      ]);

      setSnapshot(latestData);

      setHistory(
        [...historyData].reverse(),
      );

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


  if (snapshot === null) {
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


        <SensorControl />


        {error !== null && (
          <div className="error">
            {error}
          </div>
        )}


        <div className="empty-state">
          No monitoring data available yet.
          Start the sensor to begin collecting data.
        </div>

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


      <SensorControl />


      {error !== null && (
        <div className="error">
          {error}
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

        <h2>
          Incident History
        </h2>

        {incidentHistory.length === 0 ? (

          <div className="empty-state">
            No incidents recorded.
          </div>

        ) : (

          <div className="table-wrapper">

            <table>

              <thead>
                <tr>
                  <th>Status</th>
                  <th>Severity</th>
                  <th>Domain</th>
                  <th>Code</th>
                  <th>Opened</th>
                </tr>
              </thead>

              <tbody>

                {incidentHistory.map(
                  (incident) => (

                    <tr key={incident.id}>

                      <td>
                        {incident.status}
                      </td>

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
                          incident.opened_at,
                        )}
                      </td>

                    </tr>

                  ),
                )}

              </tbody>

            </table>

          </div>

        )}

      </section>


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


      <section className="panel">

        <h2>
          History
        </h2>

        <p>
          Stored samples loaded:
          {" "}
          <strong>
            {history.length}
          </strong>
        </p>

      </section>

    </main>
  );
}


export default App;
