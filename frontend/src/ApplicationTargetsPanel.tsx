import type { ApplicationTargetMetric } from "./types";


function formatLatency(value: number | null): string {
  return value === null ? "Unavailable" : `${value.toFixed(1)} ms`;
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
      <h2>Application targets</h2>
      <p className="metric-note">
        Target-aware probes use the host network route. Results describe reachability and
        end-to-end probe latency, not Wi-Fi-interface binding or application transaction phases.
      </p>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Target</th>
              <th>Status</th>
              <th>Latency</th>
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
                <td>{target.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
