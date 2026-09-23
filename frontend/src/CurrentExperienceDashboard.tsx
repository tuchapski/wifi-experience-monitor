import {
  applicationTargetDashboardState,
  applicationsDashboardState,
  findingDashboardState,
  outcomeDashboardState,
  overallDashboardState,
  wifiDashboardState,
  type DashboardState,
} from "./dashboardState";
import type {
  ApplicationTargetMetric,
  IncidentRecord,
  SensorSnapshot,
} from "./types";

import "./CurrentExperienceDashboard.css";


const STATE_LABELS: Record<DashboardState, string> = {
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  unavailable: "Unavailable",
};


function number(
  value: number | null | undefined,
  suffix = "",
  maximumFractionDigits = 1,
): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toLocaleString(undefined, { maximumFractionDigits })}${suffix}`;
}


function title(value: string | null | undefined): string {
  if (!value) return "Not localized";
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}


function wifiBand(frequency: number | null): string {
  if (frequency == null) return "Band unavailable";
  if (frequency >= 5925) return "6 GHz";
  if (frequency >= 4900) return "5 GHz";
  if (frequency >= 2400) return "2.4 GHz";
  return `${frequency} MHz`;
}


function observationAge(timestamp: string): string {
  const observed = Date.parse(timestamp);
  if (!Number.isFinite(observed)) return "Update time unavailable";
  const seconds = Math.max(0, Math.round((Date.now() - observed) / 1000));
  if (seconds < 60) return `Updated ${seconds}s ago`;
  return `Updated ${Math.floor(seconds / 60)}m ago`;
}


function StateBadge({
  state,
  label,
}: {
  state: DashboardState;
  label?: string;
}) {
  return <span className={`current-state current-state-${state}`}>
    {label ?? STATE_LABELS[state]}
  </span>;
}


function PathNode({
  label,
  state,
  primary,
  secondary,
  href,
  stateLabel,
}: {
  label: string;
  state: DashboardState;
  primary: string;
  secondary: string;
  href?: string;
  stateLabel?: string;
}) {
  const content = <>
    <div className="experience-path-node-heading">
      <span>{label}</span>
      <StateBadge state={state} label={stateLabel} />
    </div>
    <strong>{primary}</strong>
    <small>{secondary}</small>
  </>;

  return <li className={`experience-path-node experience-path-node-${state}`}>
    {href ? <a href={href}>{content}</a> : <div>{content}</div>}
  </li>;
}


function KpiCard({
  label,
  value,
  context,
  state,
}: {
  label: string;
  value: string;
  context: string;
  state: DashboardState;
}) {
  return <article className="current-kpi-card">
    <div className="current-kpi-heading">
      <span>{label}</span>
      <StateBadge state={state} />
    </div>
    <strong>{value}</strong>
    <small>{context}</small>
  </article>;
}


function applicationSummary(
  targets: ApplicationTargetMetric[],
): {
  configured: number;
  passed: number;
  failed: number;
  uncertain: number;
} {
  const active = targets.filter((target) => target.status !== "disabled");
  const passed = active.filter((target) => target.status === "passed").length;
  const failed = active.filter((target) => target.status === "failed").length;
  return {
    configured: active.length,
    passed,
    failed,
    uncertain: active.length - passed - failed,
  };
}


export default function CurrentExperienceDashboard({
  snapshot,
  activeIncidents,
  waitingMessage,
}: {
  snapshot: SensorSnapshot | null;
  activeIncidents: IncidentRecord[];
  waitingMessage: string;
}) {
  if (!snapshot) {
    return <div className="empty-state">{waitingMessage}</div>;
  }

  const overallState = overallDashboardState(snapshot);
  const overallLabel = overallState === "unavailable"
    && snapshot.diagnostic?.complete === false
    ? "Incomplete evidence"
    : STATE_LABELS[overallState];

  const correlatedDomain = snapshot.correlation?.status === "correlated"
    ? snapshot.correlation.primary_domain
    : null;
  const probableDomain = correlatedDomain ?? snapshot.diagnostic?.probable_domain;

  const targets = Object.values(snapshot.connectivity.application_targets ?? {});
  const targetSummary = applicationSummary(targets);
  const applicationState = applicationsDashboardState(snapshot.connectivity.application_targets);
  const applicationStateLabel = applicationState === "warning"
    ? "Partial evidence"
    : applicationState === "unavailable" && targetSummary.configured === 0
      ? "Not configured"
      : undefined;

  const diagnosticComplete = snapshot.diagnostic?.complete === true;
  const rssiState = findingDashboardState(
    snapshot.diagnostic?.findings,
    (finding) => ["WIFI_LOW_SIGNAL", "WIFI_VERY_LOW_SIGNAL"].includes(finding.code),
    diagnosticComplete,
  );
  const reliabilityState = findingDashboardState(
    snapshot.diagnostic?.findings,
    (finding) => [
      "WIFI_HIGH_RETRIES",
      "WIFI_ELEVATED_RETRIES",
      "WIFI_TX_FAILURES",
    ].includes(finding.code),
    diagnosticComplete,
  );

  const priorityFindings = (snapshot.diagnostic?.findings ?? [])
    .filter((finding) => finding.severity === "critical" || finding.severity === "warning")
    .sort((left, right) => {
      const rank = { critical: 0, warning: 1 } as const;
      return (rank[left.severity as keyof typeof rank] ?? 2)
        - (rank[right.severity as keyof typeof rank] ?? 2);
    });

  const applicationRows = [...targets]
    .filter((target) => target.status !== "disabled")
    .sort((left, right) => {
      const rank: Record<string, number> = { failed: 0, error: 1, skipped: 2, passed: 3 };
      return (rank[left.status] ?? 4) - (rank[right.status] ?? 4);
    })
    .slice(0, 4);

  const sensorNeedsAttention = snapshot.calibration?.calibrated !== true
    || snapshot.collector_errors.length > 0;

  return <>
    <section className={`current-experience-hero current-experience-${overallState}`}
      aria-labelledby="current-experience-title">
      <div className="current-experience-main">
        <div className="current-experience-title-row">
          <div>
            <span className="eyebrow">Current experience</span>
            <h2 id="current-experience-title">{snapshot.wifi.ssid ?? "Unknown SSID"}</h2>
          </div>
          <StateBadge state={overallState} label={overallLabel} />
        </div>

        <div className="current-experience-context">
          <span>{snapshot.wifi.interface}</span>
          <span>{wifiBand(snapshot.wifi.frequency_mhz)}</span>
          <span>Channel {snapshot.wifi.channel ?? "—"}</span>
          <span>{number(snapshot.wifi.channel_width_mhz, " MHz", 0)} width</span>
          <span>BSSID {snapshot.wifi.bssid ?? "Unavailable"}</span>
        </div>

        <p className="current-experience-note">
          {snapshot.diagnostic?.complete === false
            ? "Assessment is incomplete. Missing evidence is not treated as healthy."
            : snapshot.correlation?.reason
              ?? "Current assessment is based on the latest collected evidence."}
        </p>
      </div>

      <div className="current-experience-score">
        <span>Experience score</span>
        <strong>{snapshot.experience_score?.value == null
          ? "—"
          : number(snapshot.experience_score.value, "", 1)}</strong>
        <small>{snapshot.experience_score?.value == null ? "Unavailable"
          : `/ 100 · ${number(snapshot.experience_score.coverage_percent, "%", 0)} coverage`}</small>
      </div>

      <div className="current-experience-facts">
        <div><span>Probable domain</span><strong>{title(probableDomain)}</strong></div>
        <div><span>Active incidents</span>
          <strong className={activeIncidents.length > 0 ? "status-critical" : "status-healthy"}>
            {activeIncidents.length}
          </strong>
        </div>
        <div><span>Observation</span><strong>{observationAge(snapshot.timestamp)}</strong></div>
      </div>
    </section>

    {sensorNeedsAttention && <section className="dashboard-sensor-alert" aria-label="Sensor evidence notice">
      <strong>Sensor evidence requires attention.</strong>
      <span>
        {snapshot.calibration?.calibrated !== true ? " Calibration is incomplete." : ""}
        {snapshot.collector_errors.length > 0
          ? ` ${snapshot.collector_errors.length} collector error(s) are present.`
          : ""}
      </span>
    </section>}

    <section className="panel current-experience-path" aria-labelledby="experience-path-title">
      <div className="dashboard-section-heading">
        <div>
          <span className="eyebrow">Latest observed path</span>
          <h2 id="experience-path-title">Experience path</h2>
        </div>
        <small>
          Current/latest results only. Rolling SLO and baseline evidence can still affect the
          overall assessment above.
        </small>
      </div>
      <ol className="experience-path-list">
        <PathNode
          label="Wi-Fi"
          state={wifiDashboardState(snapshot)}
          primary={number(snapshot.wifi.signal_dbm, " dBm", 0)}
          secondary={`${wifiBand(snapshot.wifi.frequency_mhz)} · Ch ${snapshot.wifi.channel ?? "—"}`}
          href="#wifi"
        />
        <PathNode
          label="Gateway"
          state={outcomeDashboardState(snapshot.connectivity.tests?.gateway)}
          primary={number(snapshot.connectivity.gateway_latency_avg_ms, " ms")}
          secondary={`${number(snapshot.connectivity.gateway_packet_loss_percent, "%")} loss`}
        />
        <PathNode
          label="Internet"
          state={outcomeDashboardState(snapshot.connectivity.tests?.internet)}
          primary={number(snapshot.connectivity.internet_latency_avg_ms, " ms")}
          secondary={`${number(snapshot.connectivity.internet_packet_loss_percent, "%")} loss`}
        />
        <PathNode
          label="DNS"
          state={outcomeDashboardState(snapshot.connectivity.tests?.dns)}
          primary={number(snapshot.connectivity.dns_latency_ms, " ms")}
          secondary={snapshot.connectivity.dns_query ?? "Query unavailable"}
        />
        <PathNode
          label="Applications"
          state={applicationState}
          stateLabel={applicationStateLabel}
          primary={targetSummary.configured === 0
            ? "No targets"
            : `${targetSummary.passed}/${targetSummary.configured} passed`}
          secondary={targetSummary.configured === 0
            ? "Configure monitored targets"
            : `${targetSummary.failed} failed · ${targetSummary.uncertain} uncertain`}
          href="#applications"
        />
      </ol>
      <p className="metric-note">
        Gateway and Internet probes are bound to the selected interface where supported.
        DNS, HTTPS and application-target probes may follow the host route. The path localizes
        observed experience domains; it is not a traceroute or proof of physical root cause.
      </p>
    </section>

    <section aria-labelledby="current-kpis-title">
      <div className="dashboard-section-heading">
        <div>
          <span className="eyebrow">Current measurements</span>
          <h2 id="current-kpis-title">Key experience indicators</h2>
        </div>
      </div>
      <div className="current-kpi-grid">
        <KpiCard
          label="RSSI"
          value={number(snapshot.wifi.signal_dbm, " dBm", 0)}
          context={`Estimated SNR ${number(snapshot.wifi.survey?.snr_db, " dB", 0)}`}
          state={rssiState}
        />
        <KpiCard
          label="TX reliability"
          value={number(snapshot.wifi_delta?.tx_retries_per_100_packets, " / 100")}
          context={`TX failures ${number(snapshot.wifi_delta?.tx_failed_percent, "%")}`}
          state={reliabilityState}
        />
        <KpiCard
          label="Gateway"
          value={number(snapshot.connectivity.gateway_latency_avg_ms, " ms")}
          context={`${number(snapshot.connectivity.gateway_packet_loss_percent, "%")} loss · ${number(snapshot.connectivity.gateway_jitter_ms, " ms")} jitter`}
          state={outcomeDashboardState(snapshot.connectivity.tests?.gateway)}
        />
        <KpiCard
          label="Internet"
          value={number(snapshot.connectivity.internet_latency_avg_ms, " ms")}
          context={`${number(snapshot.connectivity.internet_packet_loss_percent, "%")} loss · ${number(snapshot.connectivity.internet_jitter_ms, " ms")} jitter`}
          state={outcomeDashboardState(snapshot.connectivity.tests?.internet)}
        />
        <KpiCard
          label="DNS"
          value={number(snapshot.connectivity.dns_latency_ms, " ms")}
          context={snapshot.connectivity.dns_query ?? "Query unavailable"}
          state={outcomeDashboardState(snapshot.connectivity.tests?.dns)}
        />
        <KpiCard
          label="HTTPS"
          value={number(snapshot.connectivity.https_total_time_ms, " ms")}
          context={`TTFB ${number(snapshot.connectivity.https_ttfb_ms, " ms")} · HTTP ${snapshot.connectivity.https_status_code ?? "—"}`}
          state={outcomeDashboardState(snapshot.connectivity.tests?.https)}
        />
      </div>
    </section>

    <div className="dashboard-two-column">
      <section className="panel dashboard-application-summary" aria-labelledby="dashboard-applications-title">
        <div className="dashboard-section-heading">
          <div>
            <span className="eyebrow">User-defined targets</span>
            <h2 id="dashboard-applications-title">Applications</h2>
          </div>
          <a className="dashboard-link" href="#applications">View applications →</a>
        </div>
        {applicationRows.length === 0 ? <div className="empty-state">
          No enabled application targets are available in this snapshot.
        </div> : <ul className="dashboard-target-list">
          {applicationRows.map((target) => {
            const state = applicationTargetDashboardState(target);
            return <li key={target.name}>
              <div>
                <strong>{target.name}</strong>
                <small>{target.kind.toUpperCase()} · {target.target}
                  {target.port !== null ? `:${target.port}` : ""}</small>
              </div>
              <div className="dashboard-target-result">
                <StateBadge state={state} label={target.status.replaceAll("_", " ")} />
                <strong>{number(target.latency_ms, " ms")}</strong>
                <small>{target.fresh ? "fresh result"
                  : `cached ${number(target.age_seconds, " s", 0)}`}</small>
              </div>
            </li>;
          })}
        </ul>}
      </section>

      <section className="panel dashboard-diagnosis" aria-labelledby="dashboard-diagnosis-title">
        <div className="dashboard-section-heading">
          <div>
            <span className="eyebrow">Evidence-based assessment</span>
            <h2 id="dashboard-diagnosis-title">Current diagnosis</h2>
          </div>
          {activeIncidents.length > 0
            && <a className="dashboard-link" href="#incidents">View incidents →</a>}
        </div>
        <div className="dashboard-diagnosis-summary">
          <div><span>Diagnostic status</span>
            <strong className={`status-${snapshot.diagnostic?.overall_status ?? "info"}`}>
              {snapshot.diagnostic?.overall_status?.toUpperCase() ?? "UNKNOWN"}
            </strong>
          </div>
          <div><span>Probable domain</span><strong>{title(probableDomain)}</strong></div>
          <div><span>Correlation</span>
            <strong>{title(snapshot.correlation?.status ?? "unavailable")}</strong>
          </div>
        </div>

        {priorityFindings.length === 0 ? <p className="metric-note">
          {diagnosticComplete
            ? "No active warning or critical diagnostic findings in this sample."
            : "No warning/critical finding can be interpreted as healthy while diagnostic coverage is incomplete."}
        </p> : <ul className="dashboard-finding-list">
          {priorityFindings.slice(0, 4).map((finding) => <li key={finding.code}>
            <StateBadge state={finding.severity === "critical" ? "critical" : "warning"} />
            <div><strong>{finding.code}</strong><span>{finding.message}</span></div>
          </li>)}
        </ul>}

        {snapshot.recommendations && snapshot.recommendations.length > 0 && <details>
          <summary>Recommended actions ({snapshot.recommendations.length})</summary>
          <ul className="dashboard-recommendation-list">
            {snapshot.recommendations.map((item) => <li key={item.code}>
              <strong>{item.title}</strong>
              <span>{item.action}</span>
              <small>{item.rationale}</small>
            </li>)}
          </ul>
        </details>}
      </section>
    </div>
  </>;
}
