import type { SensorSnapshot, WifiDeltaMetrics } from "./types";

function number(value: number | null | undefined, suffix = ""): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 3 })}${suffix}`;
}

function state(value: boolean | null | undefined, yes = "Enabled", no = "Disabled"): string {
  return value == null ? "Unavailable" : value ? yes : no;
}

function intervalReason(delta: WifiDeltaMetrics | null, direction: "tx" | "rx"): string {
  if (!delta) return "Waiting for two comparable samples.";
  if (delta.unavailable_reason) return delta.unavailable_reason;
  if (delta.association_changed) return "Access point changed; waiting for comparable samples.";
  if (delta.counter_reset_detected) return "Counters reset; waiting for comparable samples.";
  const packets = direction === "tx" ? delta.tx_packets_delta : delta.rx_packets_delta;
  if (packets == null) return "Packet counters unavailable.";
  if (packets === 0) return `No ${direction.toUpperCase()} packets recorded in this interval.`;
  return "Calculated from counter changes; unavailable values indicate missing counters.";
}

export default function WifiDetails({ snapshot }: { snapshot: SensorSnapshot }) {
  const wifi = snapshot.wifi;
  const delta = snapshot.wifi_delta;
  const survey = wifi.survey;
  const surveyLabels: Record<string, string> = {
    available: "Available", partial: "Partial support", unavailable: "Unavailable",
    unsupported: "Not supported by this driver", error: "Collection error",
  };
  const rates = [
    ["Reported PHY rate", number(wifi.tx_bitrate_mbps, " Mbps"), number(wifi.rx_bitrate_mbps, " Mbps")],
    ["PHY mode", wifi.tx_phy_mode ?? "Unavailable", wifi.rx_phy_mode ?? "Unavailable"],
    ["MCS", number(wifi.tx_mcs), number(wifi.rx_mcs)],
    ["Spatial streams (NSS)", number(wifi.tx_nss), number(wifi.rx_nss)],
    ["Reported rate width", number(wifi.tx_channel_width_mhz, " MHz"), number(wifi.rx_channel_width_mhz, " MHz")],
    ["Short GI (HT/VHT)", state(wifi.tx_short_gi), state(wifi.rx_short_gi)],
  ];
  const cycle = snapshot.connection_cycle;
  const stageLabels: Record<string, string> = {
    association: "Association",
    authentication: "Authentication",
    authorization: "Authorization",
    dhcp: "IPv4 address",
    gateway: "Gateway",
    dns: "DNS",
    network_ready: "Network ready",
  };
  return (
    <>
      <section className="panel" aria-labelledby="wifi-survey-title">
        <h2 id="wifi-survey-title">RF noise and channel occupancy</h2>
        <p><strong>{survey ? surveyLabels[survey.status] ?? survey.status : "Unavailable"}</strong>
          {" — "}{survey?.reason ?? "This sample has no survey measurements."}</p>
        <div className="wifi-metric-grid">
          <div><span>Noise floor · driver</span><strong>{number(survey?.noise_dbm, " dBm")}</strong></div>
          <div><span>Estimated SNR</span><strong>{number(survey?.snr_db, " dB")}</strong></div>
          <div><span>Primary channel busy · interval</span><strong>{number(delta?.channel_utilization_percent, "%")}</strong></div>
          <div><span>Radio receive time · interval</span><strong>{number(delta?.channel_rx_percent, "%")}</strong></div>
          <div><span>Radio transmit time · interval</span><strong>{number(delta?.channel_tx_percent, "%")}</strong></div>
          <div><span>Active-time delta · denominator</span><strong>{number(delta?.survey_active_ms_delta, " ms")}</strong></div>
        </div>
        <p className="metric-note">
          {delta?.survey_unavailable_reason ?? delta?.unavailable_reason
            ?? (delta?.survey_active_ms_delta != null
              ? "Percentages use counter changes between comparable samples, not lifetime totals."
              : "Waiting for two comparable survey samples.")}
        </p>
        <p className="metric-note">
          SNR is an estimate: current RSSI minus the noise reported for the in-use frequency.
          Driver measurements may have different averaging windows. Channel busy time includes
          activity or energy detected on the primary channel; it does not identify an interferer
          or describe the entire bonded channel. RX/TX time may be radio-wide depending on the
          driver and percentages must not be added together. Missing support is not evidence of
          a Wi-Fi failure. No scan, monitor mode or network changes are performed.
        </p>
        <details>
          <summary>Show cumulative survey counters</summary>
          <dl>
            <dt>Survey frequency</dt><dd>{number(survey?.frequency_mhz, " MHz")}</dd>
            <dt>Active time</dt><dd>{number(survey?.active_ms, " ms")}</dd>
            <dt>Busy time</dt><dd>{number(survey?.busy_ms, " ms")}</dd>
            <dt>Receive time</dt><dd>{number(survey?.rx_ms, " ms")}</dd>
            <dt>Transmit time</dt><dd>{number(survey?.tx_ms, " ms")}</dd>
          </dl>
        </details>
      </section>
      <section className="panel wifi-radio" aria-labelledby="wifi-radio-title">
        <h2 id="wifi-radio-title">Wi-Fi radio and link</h2>
        <p className="metric-note">TX is traffic sent by this notebook; RX is traffic received.
          PHY rates are reported radio rates, not measured application throughput.</p>
        <div className="wifi-metric-grid">
          <div><span>Current RSSI</span><strong>{number(wifi.signal_dbm, " dBm")}</strong></div>
          <div><span>Average RSSI · driver</span><strong>{number(wifi.signal_avg_dbm, " dBm")}</strong></div>
          <div><span>Average beacon signal</span><strong>{number(wifi.beacon_signal_avg_dbm, " dBm")}</strong></div>
          <div><span>Operating channel</span><strong>{number(wifi.channel)}</strong></div>
          <div><span>Frequency</span><strong>{number(wifi.frequency_mhz, " MHz")}</strong></div>
          <div><span>Operating channel width</span><strong>{number(wifi.channel_width_mhz, " MHz")}</strong></div>
          <div><span>Reported TX power</span><strong>{number(wifi.tx_power_dbm, " dBm")}</strong></div>
          <div><span>Association duration</span><strong>{number(wifi.connected_time_seconds, " s")}</strong></div>
        </div>
        <div className="table-wrapper">
          <table>
            <caption>Transmission and reception</caption>
            <thead><tr><th scope="col">Metric</th><th scope="col">TX</th><th scope="col">RX</th></tr></thead>
            <tbody>{rates.map(([label, tx, rx]) => (
              <tr key={label}><th scope="row">{label}</th><td>{tx}</td><td>{rx}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <p className="metric-note">Operating width comes from the interface configuration.
          TX/RX widths come from each reported rate and can differ. Unreported values remain unavailable.</p>
        <dl className="wifi-state-list">
          <dt>Association</dt><dd>{state(wifi.associated, "Associated", "Disconnected")}</dd>
          <dt>Authentication</dt><dd>{state(wifi.authenticated, "Authenticated", "Not authenticated")}</dd>
          <dt>Authorization</dt><dd>{state(wifi.authorized, "Authorized", "Not authorized")}</dd>
          <dt>WMM</dt><dd>{state(wifi.wmm_enabled)}</dd>
          <dt>Protected management frames</dt><dd>{state(wifi.mfp_enabled)}</dd>
          <dt>Power saving</dt><dd>{state(wifi.power_save)}</dd>
        </dl>
      </section>
      <section className="panel" aria-labelledby="connection-cycle-title">
        <h2 id="connection-cycle-title">Connection cycle</h2>
        {!cycle ? <p className="metric-note">No connection session has been observed yet.</p> : <>
          <div className="wifi-metric-grid">
            <div><span>Session type</span><strong>{cycle.session_type.replaceAll("_", " ")}</strong></div>
            <div><span>Current state</span><strong>{cycle.state}</strong></div>
            <div><span>Network ready estimate</span><strong>{number(cycle.total_time_ms, " ms")}</strong></div>
            <div><span>Sampling resolution</span><strong>{number(cycle.sample_resolution_ms, " ms")}</strong></div>
            <div><span>Timing source</span><strong>{cycle.timing_source?.replaceAll("_", " ") ?? "sampling"}</strong></div>
            <div><span>D-Bus monitor</span><strong>{cycle.event_monitor_status ?? "unavailable"}</strong></div>
            <div><span>NetworkManager state</span><strong>{cycle.networkmanager_state_name ?? "Unavailable"}</strong></div>
            <div><span>D-Bus events observed</span><strong>{number(cycle.networkmanager_event_count)}</strong></div>
          </div>
          <p className="metric-note">
            Started: {cycle.started_at ? new Date(cycle.started_at).toLocaleString() : "not observed"}
            {" · "}Last observed: {new Date(cycle.last_observed_at).toLocaleString()}
          </p>
          {cycle.event_monitor_reason
            ? <p className="metric-note">D-Bus monitor: {cycle.event_monitor_reason}</p>
            : null}
          <div className="table-wrapper">
            <table>
              <thead><tr><th>Stage</th><th>Status</th><th>Elapsed</th><th>Source</th><th>Evidence</th></tr></thead>
              <tbody>{Object.entries(cycle.stages).map(([key, stage]) => (
                <tr key={key}>
                  <td>{stageLabels[key] ?? key}</td>
                  <td>{stage.status}</td>
                  <td>{stage.elapsed_ms == null ? "Unknown" : `${number(stage.elapsed_ms, " ms")}${stage.estimated ? " · estimated" : ""}`}</td>
                  <td>{stage.source?.replaceAll("_", " ") ?? "sampling"}</td>
                  <td>{stage.reason}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <ul className="metric-note">{cycle.limitations.map(item => <li key={item}>{item}</li>)}</ul>
        </>}
      </section>
      <section className="panel" aria-labelledby="wifi-retries-title">
        <h2 id="wifi-retries-title">Wi-Fi retransmissions and counters</h2>
        <p className="metric-note">Observed interval: {number(delta?.interval_seconds, " s")}.
          Ratios use counter changes between comparable samples.</p>
        <div className="wifi-metric-grid">
          <div><span>Retries / 100 TX packets</span><strong>{number(delta?.tx_retries_per_100_packets)}</strong></div>
          <div><span>Failures / 100 TX packets</span><strong>{number(delta?.tx_failed_percent)}</strong></div>
          <div><span>Misc. drops / 100 RX packets</span><strong>{number(delta?.rx_drop_percent)}</strong></div>
          <div><span>TX packets · interval</span><strong>{number(delta?.tx_packets_delta)}</strong></div>
          <div><span>RX packets · interval</span><strong>{number(delta?.rx_packets_delta)}</strong></div>
          <div><span>Retries · interval</span><strong>{number(delta?.tx_retries_delta)}</strong></div>
        </div>
        <p className="metric-note">TX: {intervalReason(delta, "tx")}<br />RX: {intervalReason(delta, "rx")}</p>
        <p className="metric-note">Retries / 100 packets is a ratio of reported counters, not the percentage
          of unique packets retried. The value can exceed 100. No observed traffic does not mean 0% loss.</p>
        <details>
          <summary>Show cumulative counters reported by the driver</summary>
          <p className="metric-note">These totals may reset on reconnection or driver restart; they do not describe only the current interval.</p>
          <dl>
            <dt>TX packets</dt><dd>{number(wifi.tx_packets)}</dd>
            <dt>TX retries</dt><dd>{number(wifi.tx_retries)}</dd>
            <dt>TX failures</dt><dd>{number(wifi.tx_failed)}</dd>
            <dt>RX packets</dt><dd>{number(wifi.rx_packets)}</dd>
            <dt>RX misc. drops</dt><dd>{number(wifi.rx_drop_misc)}</dd>
            <dt>Beacon loss</dt><dd>{number(wifi.beacon_loss)}</dd>
            <dt>Beacons received</dt><dd>{number(wifi.beacon_rx)}</dd>
          </dl>
        </details>
      </section>
    </>
  );
}
