import type { ApplicationTargetMetric } from "./types";


function formatLatency(value: number | null): string {
  return value === null ? "Unavailable" : `${value.toFixed(1)} ms`;
}


function formatHttpMilestones(target: ApplicationTargetMetric): string {
  if (target.kind !== "http") return "—";
  return [
    `DNS ${formatLatency(target.dns_ms)}`,
    `TCP ${formatLatency(target.tcp_connect_ms)}`,
    `TLS ${formatLatency(target.tls_handshake_ms)}`,
    `TTFB ${formatLatency(target.ttfb_ms)}`,
  ].join(" · ");
}


export default function ApplicationTargetsPanel({
  targets,
}: {
  targets?: Record<string, ApplicationTargetMetric>;
}) {
  const items = Object.values(targets ?? {});
  if (items.length === 0) return null;

  return (
    <section className="panel">
      <h2>Current application health</h2>
      <p className="metric-note">
        Target-aware probes use the host network route. HTTP timings are cumulative milestones
        from transaction start: DNS complete, TCP connected, TLS complete, first byte and total.
        TLS is unavailable for plain HTTP.
      </p>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Target</th>
              <th>Status</th>
              <th>Total</th>
              <th>HTTP milestones</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {items.map((target) => (
              <tr key={target.name}>
                <td><strong>{target.name}</strong></td>
                <td>{target.kind.toUpperCase()}</td>
                <td>{target.target}{target.port !== null ? `:${target.port}` : ""}</td>
                <td className={`status-${target.status === "passed" ? "healthy" : target.status === "failed" ? "critical" : "info"}`}>
                  {target.status.toUpperCase()}{target.fresh ? "" : ` · cached ${target.age_seconds ?? "?"}s`}
                </td>
                <td>{formatLatency(target.latency_ms)}</td>
                <td>{formatHttpMilestones(target)}</td>
                <td>{target.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
