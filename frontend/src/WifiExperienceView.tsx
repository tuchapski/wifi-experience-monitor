import {
  findingDashboardState,
  wifiDashboardState,
  type DashboardState,
} from "./dashboardState";
import type { SensorSnapshot, WifiDeltaMetrics } from "./types";

import "./WifiExperienceView.css";


const STATUS_LABELS: Record<DashboardState, string> = {
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  unavailable: "Unavailable",
};


function number(
  value: number | null | undefined,
  suffix = "",
  maximumFractionDigits = 2,
): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toLocaleString(undefined, { maximumFractionDigits })}${suffix}`;
}


function booleanState(
  value: boolean | null | undefined,
  yes = "Enabled",
  no = "Disabled",
): string {
  return value == null ? "Unavailable" : value ? yes : no;
}


function band(frequency: number | null): string {
  if (frequency == null) return "Unavailable";
  if (frequency >= 5925) return "6 GHz";
  if (frequency >= 4900) return "5 GHz";
  if (frequency >= 2400) return "2.4 GHz";
  return `${frequency} MHz`;
}


function intervalReason(
  delta: WifiDeltaMetrics | null,
  direction: "tx" | "rx",
): string {
  if (!delta) return "Waiting for two comparable samples.";
  if (delta.unavailable_reason) return delta.unavailable_reason;
  if (delta.association_changed) {
    return "Access point changed; waiting for comparable samples.";
  }
  if (delta.counter_reset_detected) {
    return "Counters reset; waiting for comparable samples.";
  }
  const packets = direction === "tx" ? delta.tx_packets_delta : delta.rx_packets_delta;
  if (packets == null) return "Packet counters unavailable.";
  if (packets === 0) {
    return `No ${direction.toUpperCase()} packets recorded in this interval.`;
  }
  return "Calculated from counter changes; unavailable values indicate missing counters.";
}


function StatusPill({
  status,
  label,
}: {
  status: DashboardState;
  label?: string;
}) {
  return (
    <span className={`wifi-status-pill wifi-status-${status}`}>
      {label ?? STATUS_LABELS[status]}
    </span>
  );
}


function MetricCard({
  label,
  value,
  detail,
  status,
}: {
  label: string;
  value: string;
  detail?: string;
  status?: DashboardState;
}) {
  return (
    <article className="wifi-overview-metric">
      <div className="wifi-overview-metric-heading">
        <span>{label}</span>
        {status && <StatusPill status={status} />}
      </div>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}


export default function WifiExperienceView({
  snapshot,
}: {
  snapshot: SensorSnapshot;
}) {
  const wifi = snapshot.wifi;
  const delta = snapshot.wifi_delta;
  const survey = wifi.survey;
  const cycle = snapshot.connection_cycle;
  const cycleSlo = snapshot.connection_cycle_slo;

  const diagnosticComplete = snapshot.diagnostic?.complete === true;
  const wifiStatus = wifiDashboardState(snapshot);
  const rssiStatus = findingDashboardState(
    snapshot.diagnostic?.findings,
    (finding) => ["WIFI_LOW_SIGNAL", "WIFI_VERY_LOW_SIGNAL"].includes(finding.code),
    diagnosticComplete,
  );
  const reliabilityStatus = findingDashboardState(
    snapshot.diagnostic?.findings,
    (finding) => [
      "WIFI_HIGH_RETRIES",
      "WIFI_ELEVATED_RETRIES",
      "WIFI_TX_FAILURES",
    ].includes(finding.code),
    diagnosticComplete,
  );

  const associationStatus: DashboardState = wifi.associated === true
    ? "healthy"
    : wifi.associated === false
      ? "critical"
      : "unavailable";

  const surveyLabels: Record<string, string> = {
    available: "Available",
    partial: "Partial support",
    unavailable: "Unavailable",
    unsupported: "Not supported by this driver",
    error: "Collection error",
  };

  const rates = [
    [
      "Reported PHY rate",
      number(wifi.tx_bitrate_mbps, " Mbps"),
      number(wifi.rx_bitrate_mbps, " Mbps"),
    ],
    ["PHY mode", wifi.tx_phy_mode ?? "Unavailable", wifi.rx_phy_mode ?? "Unavailable"],
    ["MCS", number(wifi.tx_mcs), number(wifi.rx_mcs)],
    ["Spatial streams (NSS)", number(wifi.tx_nss), number(wifi.rx_nss)],
    [
      "Reported rate width",
      number(wifi.tx_channel_width_mhz, " MHz"),
      number(wifi.rx_channel_width_mhz, " MHz"),
    ],
    ["Short GI (HT/VHT)", booleanState(wifi.tx_short_gi), booleanState(wifi.rx_short_gi)],
  ];

  const stageLabels: Record<string, string> = {
    association: "Association",
    authentication: "Authentication",
    authorization: "Authorization",
    dhcp: "IPv4 address",
    ipv4: "IPv4 address",
    gateway: "Gateway",
    dns: "DNS",
    network_ready: "Network ready",
  };

  return (
    <>
      <section
        className={`panel wifi-experience-overview wifi-experience-${wifiStatus}`}
        aria-labelledby="wifi-experience-title"
      >
        <div className="wifi-overview-heading">
          <div>
            <span className="wifi-eyebrow">Current Wi-Fi connection</span>
            <h2 id="wifi-experience-title">{wifi.ssid ?? "Unknown SSID"}</h2>
          </div>
          <StatusPill status={wifiStatus} />
        </div>

        <div className="wifi-context-chips">
          <span>{wifi.interface}</span>
          <span>BSSID {wifi.bssid ?? "Unavailable"}</span>
          <span>{band(wifi.frequency_mhz)}</span>
          <span>Channel {wifi.channel ?? "—"}</span>
          <span>{number(wifi.channel_width_mhz, " MHz", 0)} width</span>
          <span>{number(wifi.connected_time_seconds, " s", 0)} connected</span>
        </div>

        <div className="wifi-overview-grid">
          <MetricCard
            label="Association"
            value={booleanState(wifi.associated, "Associated", "Disconnected")}
            detail={`${booleanState(wifi.authenticated, "Authenticated", "Not authenticated")} · ${
              booleanState(wifi.authorized, "Authorized", "Not authorized")
            }`}
            status={associationStatus}
          />
          <MetricCard
            label="RSSI"
            value={number(wifi.signal_dbm, " dBm", 0)}
            detail={`Driver average ${number(wifi.signal_avg_dbm, " dBm", 0)}`}
            status={rssiStatus}
          />
          <MetricCard
            label="Estimated SNR"
            value={number(survey?.snr_db, " dB", 0)}
            detail={`Noise ${number(survey?.noise_dbm, " dBm", 0)}`}
          />
          <MetricCard
            label="Channel busy"
            value={number(delta?.channel_utilization_percent, "%")}
            detail="Primary channel · observed interval"
          />
          <MetricCard
            label="TX retries"
            value={number(delta?.tx_retries_per_100_packets, " / 100")}
            detail={`TX failures ${number(delta?.tx_failed_percent, "%")}`}
            status={reliabilityStatus}
          />
          <MetricCard
            label="PHY rate"
            value={`TX ${number(wifi.tx_bitrate_mbps, " Mbps")}`}
            detail={`RX ${number(wifi.rx_bitrate_mbps, " Mbps")}`}
          />
        </div>

        <p className="metric-note">
          Status labels use existing diagnostic evidence. RF measurements without a configured
          diagnostic rule remain observational rather than being classified as healthy or degraded.
        </p>
      </section>

      <section className="panel" aria-labelledby="wifi-rf-title">
        <div className="wifi-section-heading">
          <div>
            <span className="wifi-eyebrow">Radio environment</span>
            <h2 id="wifi-rf-title">RF environment</h2>
          </div>
          <span className="wifi-support-state">
            {survey ? surveyLabels[survey.status] ?? survey.status : "Unavailable"}
          </span>
        </div>

        <p className="metric-note">
          {survey?.reason ?? "This sample has no survey measurements."}
        </p>

        <div className="wifi-metric-grid">
          <div>
            <span>Noise floor · driver</span>
            <strong>{number(survey?.noise_dbm, " dBm")}</strong>
          </div>
          <div>
            <span>Estimated SNR</span>
            <strong>{number(survey?.snr_db, " dB")}</strong>
          </div>
          <div>
            <span>Primary channel busy · interval</span>
            <strong>{number(delta?.channel_utilization_percent, "%")}</strong>
          </div>
          <div>
            <span>Radio receive time · interval</span>
            <strong>{number(delta?.channel_rx_percent, "%")}</strong>
          </div>
          <div>
            <span>Radio transmit time · interval</span>
            <strong>{number(delta?.channel_tx_percent, "%")}</strong>
          </div>
          <div>
            <span>Active-time delta · denominator</span>
            <strong>{number(delta?.survey_active_ms_delta, " ms")}</strong>
          </div>
        </div>

        <p className="metric-note">
          {delta?.survey_unavailable_reason ?? delta?.unavailable_reason
            ?? (delta?.survey_active_ms_delta != null
              ? "Percentages use counter changes between comparable samples, not lifetime totals."
              : "Waiting for two comparable survey samples.")}
        </p>
        <p className="metric-note">
          SNR is estimated from current RSSI and driver-reported noise. Channel busy describes
          activity or energy detected on the primary channel; it does not identify an interferer
          or describe the full bonded channel. RX/TX time can be radio-wide depending on the
          driver. Missing survey support is not evidence of Wi-Fi failure.
        </p>
      </section>

      <section className="panel" aria-labelledby="connection-experience-title">
        <div className="wifi-section-heading">
          <div>
            <span className="wifi-eyebrow">Connection lifecycle</span>
            <h2 id="connection-experience-title">Connection experience</h2>
          </div>
          {cycleSlo && (
            <StatusPill
              status={
                cycleSlo.status === "critical"
                  ? "critical"
                  : cycleSlo.status === "warning"
                    ? "warning"
                    : cycleSlo.status === "healthy"
                      ? "healthy"
                      : "unavailable"
              }
              label={cycleSlo.status.replaceAll("_", " ")}
            />
          )}
        </div>

        {!cycle ? (
          <div className="empty-state">No connection session has been observed yet.</div>
        ) : (
          <>
            <div className="wifi-connection-summary">
              <div>
                <span>Session type</span>
                <strong>{cycle.session_type.replaceAll("_", " ")}</strong>
              </div>
              <div>
                <span>Current state</span>
                <strong>{cycle.state}</strong>
              </div>
              <div>
                <span>Network ready estimate</span>
                <strong>{number(cycle.total_time_ms, " ms")}</strong>
              </div>
              <div>
                <span>Network-ready P95</span>
                <strong>{number(cycleSlo?.p95_ms, " ms")}</strong>
              </div>
            </div>

            <p className="metric-note">
              Started: {cycle.started_at
                ? new Date(cycle.started_at).toLocaleString()
                : "not observed"}
              {" · "}Last observed: {new Date(cycle.last_observed_at).toLocaleString()}
            </p>

            <details className="wifi-detail-disclosure">
              <summary>Connection milestones and collection evidence</summary>
              <div className="wifi-metric-grid">
                <div>
                  <span>Sampling resolution</span>
                  <strong>{number(cycle.sample_resolution_ms, " ms")}</strong>
                </div>
                <div>
                  <span>Timing source</span>
                  <strong>{cycle.timing_source?.replaceAll("_", " ") ?? "sampling"}</strong>
                </div>
                <div>
                  <span>D-Bus monitor</span>
                  <strong>{cycle.event_monitor_status ?? "unavailable"}</strong>
                </div>
                <div>
                  <span>NetworkManager state</span>
                  <strong>{cycle.networkmanager_state_name ?? "Unavailable"}</strong>
                </div>
                <div>
                  <span>D-Bus events observed</span>
                  <strong>{number(cycle.networkmanager_event_count)}</strong>
                </div>
              </div>

              {cycle.event_monitor_reason && (
                <p className="metric-note">
                  D-Bus monitor: {cycle.event_monitor_reason}
                </p>
              )}

              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Stage</th>
                      <th>Status</th>
                      <th>Elapsed</th>
                      <th>Source</th>
                      <th>Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(cycle.stages).map(([key, stage]) => (
                      <tr key={key}>
                        <td>{stageLabels[key] ?? key}</td>
                        <td>{stage.status}</td>
                        <td>
                          {stage.elapsed_ms == null
                            ? "Unknown"
                            : `${number(stage.elapsed_ms, " ms")}${
                              stage.estimated ? " · estimated" : ""
                            }`}
                        </td>
                        <td>{stage.source?.replaceAll("_", " ") ?? "sampling"}</td>
                        <td>{stage.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <ul className="metric-note">
                {cycle.limitations.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </details>

            {cycleSlo && (
              <details className="wifi-detail-disclosure">
                <summary>Rolling connection-cycle SLO</summary>
                <div className="wifi-metric-grid">
                  <div>
                    <span>SLO status</span>
                    <strong>{cycleSlo.status.replaceAll("_", " ")}</strong>
                  </div>
                  <div>
                    <span>Network-ready P95</span>
                    <strong>{number(cycleSlo.p95_ms, " ms")}</strong>
                  </div>
                  <div>
                    <span>Measured cycles</span>
                    <strong>{cycleSlo.sample_count} / {cycleSlo.window_size}</strong>
                  </div>
                  <div>
                    <span>Minimum samples</span>
                    <strong>{cycleSlo.minimum_samples}</strong>
                  </div>
                  <div>
                    <span>Warning threshold</span>
                    <strong>{number(cycleSlo.warning_threshold_ms, " ms")}</strong>
                  </div>
                  <div>
                    <span>Critical threshold</span>
                    <strong>{number(cycleSlo.critical_threshold_ms, " ms")}</strong>
                  </div>
                </div>

                <p className="metric-note">{cycleSlo.reason}</p>

                {cycleSlo.stages && Object.keys(cycleSlo.stages).length > 0 && (
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>Milestone</th>
                          <th>Status</th>
                          <th>P95 from start</th>
                          <th>Samples</th>
                          <th>Warning</th>
                          <th>Critical</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(cycleSlo.stages).map(([key, stage]) => (
                          <tr key={key}>
                            <td>{stageLabels[key] ?? stage.label}</td>
                            <td>
                              <strong className={`status-${stage.status}`}>
                                {stage.status.replaceAll("_", " ")}
                              </strong>
                            </td>
                            <td>{number(stage.p95_ms, " ms")}</td>
                            <td>{stage.sample_count} / {cycleSlo.window_size}</td>
                            <td>{number(stage.warning_threshold_ms, " ms")}</td>
                            <td>{number(stage.critical_threshold_ms, " ms")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="metric-note">
                      Milestone P95 is elapsed time from connection start to that observation.
                      It is not the isolated duration of the preceding protocol phase.
                    </p>
                  </div>
                )}
              </details>
            )}
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="wifi-link-title">
        <div className="wifi-section-heading">
          <div>
            <span className="wifi-eyebrow">Associated link</span>
            <h2 id="wifi-link-title">Link &amp; PHY</h2>
          </div>
        </div>

        <div className="wifi-metric-grid">
          <div>
            <span>Current RSSI</span>
            <strong>{number(wifi.signal_dbm, " dBm")}</strong>
          </div>
          <div>
            <span>Average RSSI · driver</span>
            <strong>{number(wifi.signal_avg_dbm, " dBm")}</strong>
          </div>
          <div>
            <span>Average beacon signal</span>
            <strong>{number(wifi.beacon_signal_avg_dbm, " dBm")}</strong>
          </div>
          <div>
            <span>Reported TX power</span>
            <strong>{number(wifi.tx_power_dbm, " dBm")}</strong>
          </div>
          <div>
            <span>Reported TX PHY rate</span>
            <strong>{number(wifi.tx_bitrate_mbps, " Mbps")}</strong>
          </div>
          <div>
            <span>Reported RX PHY rate</span>
            <strong>{number(wifi.rx_bitrate_mbps, " Mbps")}</strong>
          </div>
        </div>

        <dl className="wifi-state-list">
          <dt>Association</dt>
          <dd>{booleanState(wifi.associated, "Associated", "Disconnected")}</dd>
          <dt>Authentication</dt>
          <dd>{booleanState(wifi.authenticated, "Authenticated", "Not authenticated")}</dd>
          <dt>Authorization</dt>
          <dd>{booleanState(wifi.authorized, "Authorized", "Not authorized")}</dd>
          <dt>WMM</dt>
          <dd>{booleanState(wifi.wmm_enabled)}</dd>
          <dt>Protected management frames</dt>
          <dd>{booleanState(wifi.mfp_enabled)}</dd>
          <dt>Power saving</dt>
          <dd>{booleanState(wifi.power_save)}</dd>
        </dl>

        <details className="wifi-detail-disclosure">
          <summary>PHY rate details</summary>
          <p className="metric-note">
            TX is traffic sent by this notebook; RX is traffic received. PHY rates are reported
            radio rates, not measured application throughput.
          </p>
          <div className="table-wrapper">
            <table>
              <caption>Transmission and reception</caption>
              <thead>
                <tr>
                  <th scope="col">Metric</th>
                  <th scope="col">TX</th>
                  <th scope="col">RX</th>
                </tr>
              </thead>
              <tbody>
                {rates.map(([label, tx, rx]) => (
                  <tr key={label}>
                    <th scope="row">{label}</th>
                    <td>{tx}</td>
                    <td>{rx}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="metric-note">
            Operating width comes from the interface configuration. TX/RX widths come from each
            reported rate and can differ. Unreported values remain unavailable.
          </p>
        </details>
      </section>

      <section className="panel" aria-labelledby="wifi-reliability-title">
        <div className="wifi-section-heading">
          <div>
            <span className="wifi-eyebrow">Observed interval</span>
            <h2 id="wifi-reliability-title">Reliability</h2>
          </div>
          <StatusPill status={reliabilityStatus} />
        </div>

        <p className="metric-note">
          Observed interval: {number(delta?.interval_seconds, " s")}. Ratios use counter changes
          between comparable samples.
        </p>

        <div className="wifi-metric-grid">
          <div>
            <span>Retries / 100 TX packets</span>
            <strong>{number(delta?.tx_retries_per_100_packets)}</strong>
          </div>
          <div>
            <span>Failures / 100 TX packets</span>
            <strong>{number(delta?.tx_failed_percent)}</strong>
          </div>
          <div>
            <span>Misc. drops / 100 RX packets</span>
            <strong>{number(delta?.rx_drop_percent)}</strong>
          </div>
          <div>
            <span>TX packets · interval</span>
            <strong>{number(delta?.tx_packets_delta)}</strong>
          </div>
          <div>
            <span>RX packets · interval</span>
            <strong>{number(delta?.rx_packets_delta)}</strong>
          </div>
          <div>
            <span>Retries · interval</span>
            <strong>{number(delta?.tx_retries_delta)}</strong>
          </div>
        </div>

        <p className="metric-note">
          TX: {intervalReason(delta, "tx")}
          <br />
          RX: {intervalReason(delta, "rx")}
        </p>
        <p className="metric-note">
          Retries / 100 packets is a ratio of reported counters, not the percentage of unique
          packets retried. It can exceed 100. No observed traffic does not mean 0% loss.
        </p>
      </section>

      <section className="panel wifi-advanced" aria-labelledby="wifi-advanced-title">
        <div className="wifi-section-heading">
          <div>
            <span className="wifi-eyebrow">Technical evidence</span>
            <h2 id="wifi-advanced-title">Advanced driver metrics</h2>
          </div>
        </div>

        <p className="metric-note">
          Cumulative counters are useful for evidence and troubleshooting but do not describe only
          the latest sampling interval. They can reset after reassociation, driver restart or reboot.
        </p>

        <details className="wifi-detail-disclosure">
          <summary>Cumulative RF survey counters</summary>
          <dl>
            <dt>Survey frequency</dt>
            <dd>{number(survey?.frequency_mhz, " MHz")}</dd>
            <dt>Active time</dt>
            <dd>{number(survey?.active_ms, " ms")}</dd>
            <dt>Busy time</dt>
            <dd>{number(survey?.busy_ms, " ms")}</dd>
            <dt>Receive time</dt>
            <dd>{number(survey?.rx_ms, " ms")}</dd>
            <dt>Transmit time</dt>
            <dd>{number(survey?.tx_ms, " ms")}</dd>
          </dl>
        </details>

        <details className="wifi-detail-disclosure">
          <summary>Cumulative Wi-Fi counters</summary>
          <dl>
            <dt>TX packets</dt>
            <dd>{number(wifi.tx_packets)}</dd>
            <dt>TX retries</dt>
            <dd>{number(wifi.tx_retries)}</dd>
            <dt>TX failures</dt>
            <dd>{number(wifi.tx_failed)}</dd>
            <dt>RX packets</dt>
            <dd>{number(wifi.rx_packets)}</dd>
            <dt>RX misc. drops</dt>
            <dd>{number(wifi.rx_drop_misc)}</dd>
            <dt>Beacon loss</dt>
            <dd>{number(wifi.beacon_loss)}</dd>
            <dt>Beacons received</dt>
            <dd>{number(wifi.beacon_rx)}</dd>
            <dt>Beacon interval</dt>
            <dd>{number(wifi.beacon_interval_ms, " ms")}</dd>
            <dt>DTIM period</dt>
            <dd>{number(wifi.dtim_period)}</dd>
            <dt>Inactive time</dt>
            <dd>{number(wifi.inactive_time_ms, " ms")}</dd>
          </dl>
        </details>
      </section>
    </>
  );
}
