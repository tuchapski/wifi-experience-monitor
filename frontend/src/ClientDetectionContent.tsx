import type { ClientDetection, DetectionFinding, FindingStatus } from "./agentTypes";

const DOMAIN: Record<string, string> = { wifi_rf: "Wi-Fi", local_network: "Local network", dns: "DNS", internet: "Internet", application: "Application" };
const STATUS: Record<FindingStatus, string> = { unknown: "Evidence incomplete", normal: "Within rule", candidate: "Awaiting confirmation", active: "Confirmed", recovering: "Confirming recovery", recovered: "Recovery confirmed" };
const SUMMARY = { disabled: "Detection disabled", pending_profile: "Waiting for Agent to apply profile", unknown: "Evidence incomplete", observed_ok: "No rule violation observed", candidate: "Awaiting confirmation", active: "Active degradation", recovering: "Recovery in progress" };
const ORDER: Record<FindingStatus, number> = { active: 0, recovering: 1, candidate: 2, unknown: 3, recovered: 4, normal: 5 };

function reading(value: boolean | number | null, unit: string | null): string {
  if (value === null || (typeof value === "number" && !Number.isFinite(value))) return "—";
  if (typeof value === "boolean") return value ? "Success" : "Failed";
  return `${Number.isInteger(value) ? value : value.toFixed(1)}${unit ? ` ${unit}` : ""}`;
}

function Finding({ item }: { item: DetectionFinding }) {
  return <article className={`detector-finding detector-${item.status}`}>
    <div className="detector-finding-heading"><strong>{DOMAIN[item.domain]} · {item.label}</strong><span>{STATUS[item.status]}</span></div>
    <p>{item.reason}</p>
    <div className="detector-measurements"><strong>{item.status === "unknown" ? "—" : reading(item.value, item.unit)}</strong>
      {item.objective !== null && <span>Objective ≤ {reading(item.objective, item.unit)}</span>}
      <span>{item.target ?? "Wi-Fi association"}</span>
    </div>
    <details><summary>Rule and reference</summary>
      <dl>
        <div><dt>Rule</dt><dd>{item.kind === "relative" ? "Change against contextual reference" : item.kind === "availability" ? "Explicit test outcome" : "Configured objective"}</dd></div>
        <div><dt>Observed duration</dt><dd>{item.observed_duration_seconds.toFixed(0)}s · {item.consecutive_samples} consecutive measurement(s)</dd></div>
        {item.since && <div><dt>Since</dt><dd>{new Date(item.since).toLocaleString()}</dd></div>}
        {item.observed_at && <div><dt>Last observation</dt><dd>{new Date(item.observed_at).toLocaleString()}</dd></div>}
        {item.evidence_gap && <div><dt>Coverage</dt><dd>Evidence gap; duration does not count unobserved intervals.</dd></div>}
        {item.status === "unknown" && item.previous_status && <div><dt>Previous state</dt><dd>{item.previous_status} · recovery remains unconfirmed</dd></div>}
        <div><dt>Reference</dt><dd>{item.baseline.status === "ready" ? `Frozen · ${item.baseline.samples} samples` : item.baseline.status === "forming" ? `Forming · ${item.baseline.samples} successful samples` : "Not used for this rule"}</dd></div>
        {item.baseline.status === "ready" && <div><dt>Expected range</dt><dd>Median {reading(item.baseline.median, item.unit)} · p95 {reading(item.baseline.p95, item.unit)} · upper limit {reading(item.baseline.upper_limit, item.unit)}</dd></div>}
        {item.baseline.established_at && <div><dt>Reference established</dt><dd>{new Date(item.baseline.established_at).toLocaleString()}</dd></div>}
        <div><dt>Context</dt><dd>{[item.context.ssid, item.context.band, item.context.interface, item.context.location].filter(Boolean).join(" · ")}</dd></div>
      </dl>
    </details>
  </article>;
}

export default function ClientDetectionContent({ data, elapsedSeconds = 0 }: { data: ClientDetection; elapsedSeconds?: number }) {
  const findings = data.findings.map((item) => {
    const age = item.observed_at ? (Date.parse(data.evaluated_at) - Date.parse(item.observed_at)) / 1000 + elapsedSeconds : Infinity;
    return age > 30 || !Number.isFinite(age)
      ? { ...item, status: "unknown" as const, previous_status: item.status === "unknown" ? item.previous_status : item.status, evidence_gap: true, reason: "Fresh evidence is unavailable; recovery is not confirmed." }
      : item;
  }).sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const status = data.enabled && data.status !== "pending_profile" && (elapsedSeconds > 30 || findings.some(item => item.status === "unknown"))
    && !findings.some(item => item.status === "active") ? "unknown" : data.status;
  const attention = findings.filter(item => ["active", "candidate", "recovering"].includes(item.status)
    || (item.status === "unknown" && ["active", "recovering"].includes(item.previous_status ?? "")));
  const other = findings.filter(item => !attention.includes(item));
  return <div className="client-detector-content">
    <div className="detector-summary" role="status"><strong>{SUMMARY[status]}</strong><span>{findings.filter(item => item.status === "active").length} confirmed rule(s)</span></div>
    {!data.enabled && <p>Configure this client's targets and objectives, then enable detection. Existing tests continue with the Agent environment settings.</p>}
    {data.status === "pending_profile" && <p>The Agent applies changes after its running probes finish. Measurements from the previous profile cannot confirm the new rules.</p>}
    <div className="detector-findings">{attention.map(item => <Finding item={item} key={item.rule_id} />)}</div>
    {other.length > 0 && <details className="detector-all-rules"><summary>All other rules and references ({other.length})</summary><div className="detector-findings">{other.map(item => <Finding item={item} key={item.rule_id} />)}</div></details>}
    <p className="detector-note">Explicit failed tests are shown immediately. Performance changes require distinct observations over the configured duration. Gaps do not confirm recovery.</p>
    <details className="detector-limitations"><summary>Measurement limits</summary><ul>{data.limitations.map(text => <li key={text}>{text}</li>)}</ul><small>Detector {data.detector_version} · Profile {data.profile_version ?? "not configured"} · Applied {data.applied_version ?? "not reported"}</small></details>
  </div>;
}
