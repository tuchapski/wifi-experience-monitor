import type { ServiceSloMetrics } from "./types";

function number(value: number | null, suffix = ""): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
}

export default function ServiceSloPanel({ slo }: { slo?: ServiceSloMetrics | null }) {
  if (!slo) {
    return <section className="panel"><h2>Synthetic service SLO</h2>
      <p className="metric-note">No rolling service-SLO assessment is stored in this sample.</p>
    </section>;
  }

  return <section className="panel" aria-labelledby="service-slo-title">
    <h2 id="service-slo-title">Synthetic service SLA/SLO</h2>
    <p className="metric-note">
      Rolling window: {slo.window_size} executions · minimum {slo.minimum_samples} definitive
      results per dimension. Collection errors are shown separately and do not count as service
      failures.
    </p>
    <div className="diagnostic-overview">
      <div><span>Overall SLO status</span><strong className={`status-${slo.status}`}>
        {slo.status.replaceAll("_", " ").toUpperCase()}</strong></div>
      <div><span>Policy</span><strong>{slo.enabled ? "Enabled" : "Disabled"}</strong></div>
      <div><span>Fresh execution</span><strong>{slo.fresh ? "Yes" : "No"}</strong></div>
    </div>
    <p className="metric-note">{slo.reason}</p>
    <div className="table-wrapper"><table>
      <thead><tr><th>Service</th><th>Status</th><th>Availability</th><th>P95 latency</th>
        <th>P95 packet loss</th><th>Success / Failure / Error</th></tr></thead>
      <tbody>{Object.entries(slo.services).map(([name, metric]) => <tr key={name}>
        <td>{name.toUpperCase()}</td>
        <td><strong className={`status-${metric.status}`}>
          {metric.status.replaceAll("_", " ")}</strong></td>
        <td>{number(metric.availability_percent, "%")}
          <br /><small>warning &lt; {metric.availability_warning_percent}% ·
            critical &lt; {metric.availability_critical_percent}%</small></td>
        <td>{number(metric.latency_p95_ms, " ms")}
          <br /><small>{metric.latency_sample_count} measured · warning ≥
            {" "}{number(metric.latency_p95_warning_ms, " ms")}</small></td>
        <td>{metric.packet_loss_p95_warning_percent == null ? "Not applicable" :
          <>{number(metric.packet_loss_p95_percent, "%")}
            <br /><small>{metric.packet_loss_sample_count} measured · warning ≥
              {" "}{number(metric.packet_loss_p95_warning_percent, "%")}</small></>}</td>
        <td>{metric.success_count} / {metric.failure_count} / {metric.measurement_error_count}
          <br /><small>{metric.attempt_count} attempts in window</small></td>
      </tr>)}</tbody>
    </table></div>
    <p className="metric-note">
      Availability uses only definitive passed/failed executions. Latency P95 uses successful
      measurements. Cached results are not re-counted; missing values remain unavailable.
    </p>
  </section>;
}
