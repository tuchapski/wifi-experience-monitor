import { useEffect, useState } from "react";
import Plot from "react-plotly.js";

import {
  getHistory,
  getLatestSnapshot,
} from "./api";

import type {
  HistoryRecord,
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


function App() {
  const [snapshot, setSnapshot] =
    useState<SensorSnapshot | null>(null);

  const [history, setHistory] =
    useState<HistoryRecord[]>([]);

  const [error, setError] =
    useState<string | null>(null);


  async function refresh() {
    try {
      const [
        latestData,
        historyData,
      ] = await Promise.all([
        getLatestSnapshot(),
        getHistory(100),
      ]);

      setSnapshot(
        latestData,
      );

      setHistory(
        [...historyData].reverse(),
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

        <h1>
          Wi-Fi Experience Monitor
        </h1>

        {error !== null ? (
          <div className="error">
            {error}
          </div>
        ) : (
          <p>
            Loading sensor data...
          </p>
        )}

      </main>
    );
  }


  const timestamps = history.map(
    (item) => item.timestamp,
  );

  const signalHistory = history.map(
    (item) => item.signal_dbm,
  );

  const gatewayHistory = history.map(
    (item) =>
      item.gateway_latency_avg_ms,
  );

  const internetHistory = history.map(
    (item) =>
      item.internet_latency_avg_ms,
  );

  const retriesHistory = history.map(
    (item) =>
      item.tx_retries_per_100_packets,
  );


  return (
    <main className="page">

      <header className="header">

        <div>
          <h1>
            Wi-Fi Experience Monitor
          </h1>

          <p>
            {snapshot.wifi.ssid ??
              "Unknown SSID"}

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


      {error !== null && (
        <div className="error">
          {error}
        </div>
      )}


      {snapshot.diagnostic !== null && (
        <section className="diagnostic-overview">

          <div>
            <span>
              Overall Experience
            </span>

            <strong
              className={
                `status-${snapshot.diagnostic.overall_status}`
              }
            >
              {formatStatus(
                snapshot.diagnostic.overall_status,
              )}
            </strong>
          </div>


          <div>
            <span>
              Probable Domain
            </span>

            <strong>
              {snapshot.diagnostic
                .probable_domain ??
                "None"}
            </strong>
          </div>

        </section>
      )}


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

          <small>
            Avg{" "}
            {formatNumber(
              snapshot.wifi.signal_avg_dbm,
              " dBm",
            )}
          </small>
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

          <small>
            Loss{" "}
            {formatNumber(
              snapshot.connectivity
                .gateway_packet_loss_percent,
              "%",
            )}
          </small>
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

          <small>
            Loss{" "}
            {formatNumber(
              snapshot.connectivity
                .internet_packet_loss_percent,
              "%",
            )}
          </small>
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

          <small>
            {snapshot.connectivity
              .dns_success
              ? "OK"
              : "FAILED"}
          </small>
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

          <small>
            HTTP{" "}
            {snapshot.connectivity
              .https_status_code ??
              "N/A"}
          </small>
        </div>


        <div className="card">
          <span>
            TX Retries
          </span>

          <strong>
            {formatNumber(
              snapshot.wifi_delta
                ?.tx_retries_per_100_packets ??
                null,
            )}
          </strong>

          <small>
            retries / 100 TX packets
          </small>
        </div>

      </section>


      <section className="details">

        <div className="panel">

          <h2>
            Wi-Fi
          </h2>

          <dl>

            <dt>
              BSSID
            </dt>

            <dd>
              {snapshot.wifi.bssid ??
                "N/A"}
            </dd>


            <dt>
              Channel
            </dt>

            <dd>
              {snapshot.wifi.channel ??
                "N/A"}

              {" / "}

              {snapshot.wifi
                .channel_width_mhz ??
                "N/A"}

              MHz
            </dd>


            <dt>
              Frequency
            </dt>

            <dd>
              {formatNumber(
                snapshot.wifi.frequency_mhz,
                " MHz",
              )}
            </dd>


            <dt>
              PHY
            </dt>

            <dd>
              {snapshot.wifi.tx_phy_mode ??
                "N/A"}
            </dd>


            <dt>
              TX Rate
            </dt>

            <dd>
              {formatNumber(
                snapshot.wifi
                  .tx_bitrate_mbps,
                " Mbps",
              )}
            </dd>


            <dt>
              RX Rate
            </dt>

            <dd>
              {formatNumber(
                snapshot.wifi
                  .rx_bitrate_mbps,
                " Mbps",
              )}
            </dd>


            <dt>
              MCS
            </dt>

            <dd>
              TX{" "}
              {snapshot.wifi.tx_mcs ??
                "N/A"}

              {" / "}

              RX{" "}
              {snapshot.wifi.rx_mcs ??
                "N/A"}
            </dd>


            <dt>
              NSS
            </dt>

            <dd>
              TX{" "}
              {snapshot.wifi.tx_nss ??
                "N/A"}

              {" / "}

              RX{" "}
              {snapshot.wifi.rx_nss ??
                "N/A"}
            </dd>


            <dt>
              Beacon Loss
            </dt>

            <dd>
              {snapshot.wifi.beacon_loss ??
                "N/A"}
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
                .ipv4_address ??
                "N/A"}

              /

              {snapshot.network
                .prefix_length ??
                "N/A"}
            </dd>


            <dt>
              Gateway
            </dt>

            <dd>
              {snapshot.network.gateway ??
                "N/A"}
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


            <dt>
              Internet
            </dt>

            <dd>
              {snapshot.connectivity
                .internet_reachable
                ? "Reachable"
                : "Unavailable"}
            </dd>


            <dt>
              Association
            </dt>

            <dd>
              {snapshot.wifi.associated
                ? "Associated"
                : "Disconnected"}
            </dd>


            <dt>
              Authentication
            </dt>

            <dd>
              {snapshot.wifi.authenticated
                ? "Authenticated"
                : "Not authenticated"}
            </dd>


            <dt>
              WMM
            </dt>

            <dd>
              {snapshot.wifi.wmm_enabled
                ? "Enabled"
                : "Disabled"}
            </dd>


            <dt>
              MFP
            </dt>

            <dd>
              {snapshot.wifi.mfp_enabled
                ? "Enabled"
                : "Disabled"}
            </dd>


            <dt>
              Power Save
            </dt>

            <dd>
              {snapshot.wifi.power_save
                ? "Enabled"
                : "Disabled"}
            </dd>

          </dl>

        </div>

      </section>


      <section className="chart">

        <h2>
          Wi-Fi Signal History
        </h2>

        <Plot
          data={[
            {
              x: timestamps,
              y: signalHistory,
              type: "scatter",
              mode: "lines",
              name: "RSSI",
            },
          ]}
          layout={{
            autosize: true,
            height: 320,

            margin: {
              l: 60,
              r: 20,
              t: 20,
              b: 50,
            },

            yaxis: {
              title: {
                text: "dBm",
              },
            },
          }}
          useResizeHandler
          style={{
            width: "100%",
          }}
        />

      </section>


      <section className="chart">

        <h2>
          Network Latency History
        </h2>

        <Plot
          data={[
            {
              x: timestamps,
              y: gatewayHistory,
              type: "scatter",
              mode: "lines",
              name: "Gateway",
            },
            {
              x: timestamps,
              y: internetHistory,
              type: "scatter",
              mode: "lines",
              name: "Internet",
            },
          ]}
          layout={{
            autosize: true,
            height: 320,

            margin: {
              l: 60,
              r: 20,
              t: 20,
              b: 50,
            },

            yaxis: {
              title: {
                text: "Latency (ms)",
              },
            },
          }}
          useResizeHandler
          style={{
            width: "100%",
          }}
        />

      </section>


      <section className="chart">

        <h2>
          Wi-Fi Retransmission History
        </h2>

        <Plot
          data={[
            {
              x: timestamps,
              y: retriesHistory,
              type: "scatter",
              mode: "lines",
              name: "TX retries",
            },
          ]}
          layout={{
            autosize: true,
            height: 320,

            margin: {
              l: 60,
              r: 20,
              t: 20,
              b: 50,
            },

            yaxis: {
              title: {
                text: "Retries / 100 TX packets",
              },
            },
          }}
          useResizeHandler
          style={{
            width: "100%",
          }}
        />

      </section>


      {snapshot.diagnostic !== null &&
        snapshot.diagnostic.findings.length > 0 && (

          <section className="diagnostic-panel">

            <h2>
              Diagnostic Findings
            </h2>

            <ul>

              {snapshot.diagnostic.findings.map(
                (finding) => (

                  <li key={finding.code}>

                    <strong>
                      {finding.severity.toUpperCase()}
                    </strong>

                    {" · "}

                    {finding.domain}

                    {" · "}

                    {finding.message}

                  </li>

                ),
              )}

            </ul>

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

    </main>
  );
}


export default App;
