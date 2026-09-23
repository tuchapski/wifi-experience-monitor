import type { AdaptiveBaselineMetrics } from "./types";

function number(value: number | null, unit = ""): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit}`;
}

export default function AdaptiveBaselinePanel({ baseline }: { baseline?: AdaptiveBaselineMetrics | null }) {
  if (!baseline) {
    return <section className="panel"><h2>Adaptive baseline</h2>
      <p className="metric-note">No adaptive-baseline assessment is stored in this sample.</p></section>;
  }

  return <section className="panel" aria-labelledby="adaptive-baseline-title">
    <h2 id="adaptive-baseline-title">Adaptive baseline · same SSID</h2>
    <p className="metric-note">
      Reference: {baseline.ssid ?? "Unknown SSID"} · last {baseline.lookback_hours} hours ·
      robust median/MAD comparison. Only fresh measurements are evaluated.
    </p>
    <div className="diagnostic-overview">
      <div><span>Baseline status</span><strong className={`status-${baseline.status}`}>
        {baseline.status.replaceAll("_", " ").toUpperCase()}</strong></div>
      <div><span>Warning deviation</span><strong>{baseline.warning_sigma} σ</strong></div>
      <div><span>Critical deviation</span><strong>{baseline.critical_sigma} σ</strong></div>
      <div><span>Minimum history</span><strong>{baseline.minimum_samples} samples</strong></div>
    </div>
    <p className="metric-note">{baseline.reason}</p>
    {baseline.metrics.length > 0 && <div className="table-wrapper"><table>
      <thead><tr><th>Metric</th><th>Status</th><th>Current</th><th>Baseline median</th>
        <th>Deviation</th><th>Reference samples</th></tr></thead>
      <tbody>{baseline.metrics.map(metric => <tr key={metric.key}>
        <td>{metric.label}</td>
        <td><strong className={`status-${metric.status}`}>{metric.status.replaceAll("_", " ")}</strong></td>
        <td>{number(metric.current, metric.unit ? ` ${metric.unit}` : "")}</td>
        <td>{number(metric.baseline_median, metric.unit ? ` ${metric.unit}` : "")}</td>
        <td>{metric.deviation_sigma == null ? "Unavailable"
          : `${number(metric.deviation_sigma)} σ ${metric.deviation_sigma > 0 ? "worse" : "better/equal"}`}</td>
        <td>{metric.sample_count} / {metric.minimum_samples} minimum</td>
      </tr>)}</tbody>
    </table></div>}
    <p className="metric-note">
      MAD is the median absolute deviation. A metric-specific scale floor prevents an almost-zero MAD
      from turning tiny changes into anomalies. Adaptive findings complement, rather than replace,
      the absolute diagnostic thresholds in the active profile.
    </p>
  </section>;
}
