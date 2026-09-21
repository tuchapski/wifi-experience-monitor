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
  const rates = [
    ["Reported PHY rate", number(wifi.tx_bitrate_mbps, " Mbps"), number(wifi.rx_bitrate_mbps, " Mbps")],
    ["PHY mode", wifi.tx_phy_mode ?? "Unavailable", wifi.rx_phy_mode ?? "Unavailable"],
    ["MCS", number(wifi.tx_mcs), number(wifi.rx_mcs)],
    ["Spatial streams (NSS)", number(wifi.tx_nss), number(wifi.rx_nss)],
    ["Reported rate width", number(wifi.tx_channel_width_mhz, " MHz"), number(wifi.rx_channel_width_mhz, " MHz")],
    ["Short GI (HT/VHT)", state(wifi.tx_short_gi), state(wifi.rx_short_gi)],
  ];
  return (
    <>
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
