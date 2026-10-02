import type { ClientExperience, ClientExperienceStatus, ExperienceMeasurement } from "./agentTypes";

const LABELS: Record<ClientExperienceStatus, string> = {
  observed_ok: "Tests responding", degraded: "Packet loss observed", failure: "Failure observed",
  partial: "Partial evidence", unavailable: "Unavailable", stale: "Stale evidence",
  collection_error: "Collection error",
};

function reading(item: ExperienceMeasurement): string {
  if (item.value === null || (typeof item.value === "number" && !Number.isFinite(item.value))) return "—";
  if (typeof item.value === "boolean") return item.value ? "Success" : "Failed";
  if (typeof item.value === "string") return item.value;
  return `${Number.isInteger(item.value) ? item.value : item.value.toFixed(1)}${item.unit ? ` ${item.unit}` : ""}`;
}

export default function ClientExperienceContent({ data, elapsedSeconds = 0 }: {
  data: ClientExperience;
  elapsedSeconds?: number;
}) {
  const snapshotAge = data.state_observed_at
    ? (Date.parse(data.evaluated_at) - Date.parse(data.state_observed_at)) / 1000 : 0;
  const expired = elapsedSeconds > data.max_measurement_age_seconds
    || snapshotAge + elapsedSeconds > data.max_measurement_age_seconds;
  const domains = data.domains.map((domain) => {
    const outcome = domain.measurements[0];
    const supporting = domain.status === "collection_error"
      ? domain.measurements.filter((item) => item.metric.endsWith("_collection_error"))
      : domain.status === "degraded"
        ? [outcome, ...domain.measurements.filter((item) => item.metric.endsWith("_packet_loss_percent"))]
        : [outcome];
    const outcomeExpired = supporting.some((item) => item?.quality === "current"
      && item.age_seconds !== null
      && item.age_seconds + elapsedSeconds > data.max_measurement_age_seconds);
    const status: ClientExperienceStatus = expired || outcomeExpired ? "stale" : domain.status;
    return { ...domain, status };
  });
  const current = domains.filter((domain) =>
    ["observed_ok", "failure", "degraded"].includes(domain.status)).length;
  const statuses = new Set(domains.map((domain) => domain.status));
  const overall: ClientExperienceStatus = statuses.has("failure") ? "failure"
    : statuses.has("degraded") ? "degraded"
    : statuses.size === 1 && statuses.has("observed_ok") ? "observed_ok"
    : statuses.size === 1 && statuses.has("stale") ? "stale"
    : statuses.size === 1 && statuses.has("unavailable") ? "unavailable" : "partial";

  return <section className="agent-panel client-experience" aria-label="Client experience now">
    <div className="agent-panel-heading">
      <div>
        <span className="agent-eyebrow">Individual client experience</span>
        <h2>Experience now</h2>
        <p>Availability of this client and its configured service targets.</p>
      </div>
      <span className={`client-experience-status experience-${overall}`} role="status">{LABELS[overall]}</span>
    </div>
    <div className="client-experience-coverage">
      <strong>{current}/{data.total_outcomes} current outcomes</strong>
      <span>{data.agent_online ? "Agent online" : "Agent offline"} · Each test keeps its own observation time</span>
    </div>
    <div className="client-experience-grid">
      {domains.map((domain) => {
        const outcome = domain.measurements[0];
        const visibleLatency = domain.measurements.find((item) =>
          item.metric.endsWith("latency_ms") || item.metric.endsWith("total_ms") || item.metric.endsWith("rssi_dbm"));
        const currentReading = visibleLatency?.quality === "current" && !expired
          && visibleLatency.age_seconds !== null
          && visibleLatency.age_seconds + elapsedSeconds <= data.max_measurement_age_seconds;
        const statusLabel = domain.domain === "wifi_rf" && domain.status === "observed_ok"
          ? "Associated" : LABELS[domain.status];
        return <article className={`client-experience-domain experience-${domain.status}`} key={domain.domain}>
          <header><h3>{domain.label}</h3><span>{statusLabel}</span></header>
          <strong className="client-experience-reading">{visibleLatency && currentReading ? reading(visibleLatency) : "—"}</strong>
          <p className="client-experience-target">{domain.target ?? (domain.domain === "wifi_rf" ? "Current association" : "Target not reported")}</p>
          <p>{domain.status === "stale" ? "Current availability cannot be confirmed from these readings." : domain.explanation}</p>
          <details>
            <summary>View evidence</summary>
            <dl>
              {domain.measurements.map((item) => {
                const aged = item.quality === "current" && item.age_seconds !== null
                  && item.age_seconds + elapsedSeconds > data.max_measurement_age_seconds;
                const quality = expired || aged ? "stale" : item.quality;
                return <div key={item.metric}>
                  <dt>{item.label}</dt>
                  <dd><strong>{reading(item)}</strong><small>{quality === "legacy" ? "Observation time not reported" : quality}</small>
                    {item.observed_at && <time dateTime={item.observed_at}>{new Date(item.observed_at).toLocaleTimeString()}</time>}
                    {item.source && <small>{item.source} · {item.sample_count ?? "—"} measurement(s){item.interval_seconds !== null ? ` · ${item.interval_seconds}s interval` : ""}</small>}
                    {item.profile_version && <small>Profile {item.profile_version}</small>}
                  </dd>
                </div>;
              })}
            </dl>
            {outcome?.quality === "legacy" && <p>Update the Agent to report each test's own observation time.</p>}
          </details>
        </article>;
      })}
    </div>
    <p className="client-experience-note">Successful replies describe availability. Latency is shown without a performance objective; this view does not assign a root cause.</p>
    {data.collector_errors.length > 0 && <details className="client-experience-warnings">
      <summary>Collection warnings ({data.collector_errors.length})</summary>
      <ul>{data.collector_errors.map((message, index) => <li key={index}>{message}</li>)}</ul>
    </details>}
  </section>;
}
