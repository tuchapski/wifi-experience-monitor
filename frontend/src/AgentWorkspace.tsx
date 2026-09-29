import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  getAgent,
  getAgents,
  getAgentState,
  getAgentTelemetry,
  renameAgent,
} from "./agentApi";
import DiagnosticsWorkspace from "./DiagnosticsWorkspace";
import GlobalCollectionIndicator from "./GlobalCollectionIndicator";
import ManagedAgentCard from "./ManagedAgentCard";
import { diagnosticsAgentHash, parseWorkspaceRoute } from "./diagnosticRoutes";
import RecordingDetail from "./RecordingDetail";
import type {
  AgentCurrentState,
  AgentSummary,
  AgentWithState,
  LinkScore,
  TelemetryPoint,
} from "./agentTypes";
import { describeWifiConnection } from "./wifiPresentation";
import "./AgentWorkspace.css";

const TELEMETRY_METRICS = [
  { key: "wifi.rssi_dbm", label: "RSSI", unit: "dBm" },
  { key: "wifi.snr_db", label: "SNR", unit: "dB" },
  { key: "wifi.tx_rate_mbps", label: "TX rate", unit: "Mbps" },
  { key: "wifi.rx_rate_mbps", label: "RX rate", unit: "Mbps" },
  { key: "wifi.channel_utilization_percent", label: "Channel utilization", unit: "%" },
] as const;

const RANGE_OPTIONS = [
  { hours: 0.25, label: "15m" },
  { hours: 1, label: "1h" },
  { hours: 6, label: "6h" },
  { hours: 24, label: "24h" },
] as const;

const MAX_CURRENT_STATE_AGE_MS = 30_000;

function isCurrentState(agent: AgentSummary, state: AgentCurrentState | null): boolean {
  if (agent.status !== "online" || !state) return false;
  const age = Date.now() - Date.parse(state.observed_at);
  return Number.isFinite(age) && age >= -5_000 && age <= MAX_CURRENT_STATE_AGE_MS;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "Never";
  const seconds = Math.max(0, Math.round((Date.now() - Date.parse(value)) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function formatMetric(value: number | null | undefined, unit = ""): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return unit ? `${formatted} ${unit}` : formatted;
}

function statusClass(status: string): string {
  return status === "online" ? "agent-status-online" : "agent-status-offline";
}

function navigateToAgent(agentId: string): void {
  window.location.hash = `#agents/${encodeURIComponent(agentId)}`;
}

function navigateToAgents(): void {
  window.location.hash = "#agents";
}

function downsample(points: TelemetryPoint[], maxPoints = 240): TelemetryPoint[] {
  if (points.length <= maxPoints) return points;
  const stride = Math.ceil(points.length / maxPoints);
  return points.filter((_, index) => index % stride === 0 || index === points.length - 1);
}

function TelemetryChart({
  points,
  label,
  unit,
}: {
  points: TelemetryPoint[];
  label: string;
  unit: string;
}) {
  const sampled = useMemo(() => downsample(points), [points]);

  if (sampled.length === 0) {
    return (
      <article className="agent-chart-card">
        <div className="agent-chart-heading">
          <div>
            <span>{label}</span>
            <strong>—</strong>
          </div>
          <small>No telemetry in this period</small>
        </div>
        <div className="agent-chart-empty">Waiting for data</div>
      </article>
    );
  }

  const lows = sampled.map((point) => point.min_value ?? point.value);
  const highs = sampled.map((point) => point.max_value ?? point.value);
  let minimum = Math.min(...lows);
  let maximum = Math.max(...highs);
  if (minimum === maximum) {
    minimum -= 1;
    maximum += 1;
  }
  const span = maximum - minimum;
  const firstTime = Date.parse(sampled[0].observed_at);
  const lastTime = Date.parse(sampled[sampled.length - 1].observed_at);
  const timeSpan = Math.max(1, lastTime - firstTime);
  const x = (point: TelemetryPoint) =>
    16 + ((Date.parse(point.observed_at) - firstTime) / timeSpan) * 688;
  const y = (value: number) => 156 - ((value - minimum) / span) * 132;
  const polyline = sampled.map((point) => `${x(point)},${y(point.value)}`).join(" ");
  const latest = sampled[sampled.length - 1];

  return (
    <article className="agent-chart-card">
      <div className="agent-chart-heading">
        <div>
          <span>{label}</span>
          <strong>{formatMetric(latest.value, unit)}</strong>
        </div>
        <small>{latest.sample_count} samples in latest window</small>
      </div>
      <svg
        className="agent-sparkline"
        viewBox="0 0 720 176"
        role="img"
        aria-label={`${label} telemetry chart`}
      >
        <line x1="16" x2="704" y1="24" y2="24" className="agent-chart-gridline" />
        <line x1="16" x2="704" y1="90" y2="90" className="agent-chart-gridline" />
        <line x1="16" x2="704" y1="156" y2="156" className="agent-chart-gridline" />
        {sampled.map((point) => (
          <line
            key={`${point.observed_at}-${point.value}`}
            x1={x(point)}
            x2={x(point)}
            y1={y(point.max_value ?? point.value)}
            y2={y(point.min_value ?? point.value)}
            className="agent-chart-range"
          />
        ))}
        <polyline points={polyline} className="agent-chart-line" />
      </svg>
      <div className="agent-chart-axis">
        <span>{new Date(firstTime).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
        <span>{`${formatMetric(maximum, unit)} / ${formatMetric(minimum, unit)}`}</span>
        <span>{new Date(lastTime).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
      </div>
    </article>
  );
}

type ExperiencePathStatus = "success" | "failure" | "unavailable";

function experienceStatus(
  outcome: boolean | null | undefined,
  hasMeasurement: boolean,
): ExperiencePathStatus {
  if (outcome === false) return "failure";
  if (outcome === true || hasMeasurement) return "success";
  return "unavailable";
}

function ExperiencePath({
  state,
  fresh,
}: {
  state: AgentCurrentState | null;
  fresh: boolean;
}) {
  const wifi = fresh ? state?.wifi : null;
  const network = fresh ? state?.network : null;
  const steps = [
    {
      key: "wifi",
      label: "Wi-Fi / RF",
      status: experienceStatus(wifi?.connected, wifi?.rssi_dbm != null),
      statusLabel: wifi?.connected === false ? "Disconnected" : wifi?.connected ? "Connected" : "Unavailable",
      primary: formatMetric(wifi?.rssi_dbm, "dBm"),
      secondary: `SNR ${formatMetric(wifi?.snr_db, "dB")} · Util ${formatMetric(wifi?.channel_utilization_percent, "%")}`,
    },
    {
      key: "gateway",
      label: "Gateway",
      status: experienceStatus(network?.gateway_reachable, network?.gateway_latency_ms != null),
      statusLabel: network?.gateway_reachable === false ? "Unreachable" : network?.gateway_reachable ? "Reachable" : "Unavailable",
      primary: network?.gateway_reachable === false ? "Failed" : formatMetric(network?.gateway_latency_ms, "ms"),
      secondary: `Loss ${formatMetric(network?.gateway_packet_loss_percent, "%")} · Jitter ${formatMetric(network?.gateway_jitter_ms, "ms")}`,
    },
    {
      key: "dns",
      label: "DNS",
      status: experienceStatus(network?.dns_success, network?.dns_latency_ms != null),
      statusLabel: network?.dns_success === false ? "Failed" : network?.dns_success ? "Success" : "Unavailable",
      primary: network?.dns_success === false ? "Failed" : formatMetric(network?.dns_latency_ms, "ms"),
      secondary: network?.dns_success === true ? "Resolver completed" : "Resolver result unavailable",
    },
    {
      key: "internet",
      label: "Internet",
      status: experienceStatus(network?.internet_reachable, network?.internet_latency_ms != null),
      statusLabel: network?.internet_reachable === false ? "Unreachable" : network?.internet_reachable ? "Reachable" : "Unavailable",
      primary: network?.internet_reachable === false ? "Failed" : formatMetric(network?.internet_latency_ms, "ms"),
      secondary: `Loss ${formatMetric(network?.internet_packet_loss_percent, "%")} · Jitter ${formatMetric(network?.internet_jitter_ms, "ms")}`,
    },
    {
      key: "application",
      label: "Application",
      status: experienceStatus(network?.https_success, network?.https_total_ms != null),
      statusLabel: network?.https_success === false ? "Failed" : network?.https_success ? "Success" : "Unavailable",
      primary: network?.https_success === false ? "Failed" : formatMetric(network?.https_total_ms, "ms"),
      secondary: network?.https_success === false
        ? `Observed for ${formatMetric(network?.https_failure_elapsed_ms, "ms")}`
        : `TTFB ${formatMetric(network?.https_ttfb_ms, "ms")} · HTTP ${network?.https_status_code ?? "—"}`,
    },
  ] as const;

  return (
    <section className="agent-panel agent-experience-path">
      <div className="agent-panel-heading">
        <div>
          <span className="agent-eyebrow">Realtime experience</span>
          <h2>Experience Path</h2>
          <p>Current measured path from the Wi-Fi link to the configured application target.</p>
        </div>
        <small>{fresh ? "Fresh Current State" : "Waiting for fresh data"}</small>
      </div>
      <div className="agent-experience-path-grid">
        {steps.map((step, index) => (
          <article className={`agent-path-step path-${step.status}`} key={step.key}>
            <header>
              <span>{step.label}</span>
              <small><i />{step.statusLabel}</small>
            </header>
            <strong>{step.primary}</strong>
            <p>{step.secondary}</p>
            {index < steps.length - 1 && <b aria-hidden="true">→</b>}
          </article>
        ))}
      </div>
      <p className="agent-experience-path-note">
        Values are direct observations from the latest Agent state; this view does not assign root cause.
      </p>
    </section>
  );
}

type ReadinessStatus = "producing" | "verified" | "available" | "degraded" | "unavailable";

function SensorReadiness({
  agent,
  state,
  fresh,
}: {
  agent: AgentSummary;
  state: AgentCurrentState | null;
  fresh: boolean;
}) {
  const wifi = fresh ? state?.wifi : null;
  const declared = new Set(
    agent.capabilities
      .filter((capability) => capability.enabled)
      .map((capability) => capability.capability),
  );
  const surveyStatus = wifi?.survey_status;
  const channelStatus: ReadinessStatus = wifi?.channel_utilization_percent != null
    ? "producing"
    : surveyStatus === "verified"
      ? "verified"
      : surveyStatus === "degraded"
        ? "degraded"
        : surveyStatus === "unavailable"
          ? "unavailable"
          : "available";

  const rows: { label: string; status: ReadinessStatus; detail: string }[] = [
    {
      label: "Wi-Fi association",
      status: wifi?.connected === true ? "producing" : "unavailable",
      detail: wifi?.connected === true
        ? `Associated to ${wifi.ssid ?? "unknown SSID"}`
        : wifi?.connected === false
          ? "The interface is currently disconnected."
          : "No fresh association observation.",
    },
    {
      label: "Station statistics",
      status: wifi?.signal_avg_dbm != null || wifi?.tx_packets != null
        ? "producing"
        : declared.has("wifi.station_stats") ? "available" : "unavailable",
      detail: wifi?.signal_avg_dbm != null || wifi?.tx_packets != null
        ? "The driver is producing station/link statistics."
        : declared.has("wifi.station_stats")
          ? "Prerequisites are present, but no fresh station statistics were observed."
          : "This capability was not advertised at enrollment.",
    },
    {
      label: "RF survey",
      status: surveyStatus === "verified"
        ? "verified"
        : surveyStatus === "degraded"
          ? "degraded"
          : surveyStatus === "unavailable"
            ? "unavailable"
            : "available",
      detail: wifi?.survey_reason
        ?? "RF survey has not yet been verified in the current association.",
    },
    {
      label: "Channel utilization",
      status: channelStatus,
      detail: wifi?.channel_utilization_percent != null
        ? `Producing ${formatMetric(wifi.channel_utilization_percent, "%")} from active/busy survey deltas.`
        : surveyStatus === "verified"
          ? "Survey counters are verified; waiting for a second comparable sample."
          : "No validated channel-utilization observation is currently available.",
    },
    {
      label: "Wi-Fi scan",
      status: declared.has("wifi.scan") ? "available" : "unavailable",
      detail: declared.has("wifi.scan")
        ? "Prerequisites are available; active scan is intentionally not exercised automatically."
        : "This capability was not advertised at enrollment.",
    },
  ];

  const coreIssue = rows.slice(0, 2).some(
    (row) => row.status === "degraded" || row.status === "unavailable",
  );
  const optionalLimitations = rows.slice(2).some(
    (row) => row.status === "degraded" || row.status === "unavailable",
  );
  const healthTone = !fresh
    ? "stale"
    : coreIssue
      ? "attention"
      : optionalLimitations
        ? "limited"
        : "ready";
  const healthLabel = !fresh
    ? "Stale"
    : coreIssue
      ? "Attention"
      : optionalLimitations
        ? "Ready with limitations"
        : "Ready";
  const healthDetail = !fresh
    ? "Current State is stale or the Agent is offline."
    : coreIssue
      ? "Association or station evidence needs attention."
      : optionalLimitations
        ? "Core measurements are available; optional RF evidence is limited."
        : "Core runtime measurements are available.";

  return (
    <section className="agent-panel agent-readiness-panel">
      <details className="agent-capability-details agent-readiness-details">
        <summary>
          <div className="agent-capability-summary-main">
            <span className="agent-eyebrow">Sensor</span>
            <strong>Sensor health</strong>
            <small>{healthDetail}</small>
          </div>
          <div className="agent-capability-summary-meta">
            <span className={`agent-readiness-health health-${healthTone}`}>{healthLabel}</span>
            <i aria-hidden="true">⌄</i>
          </div>
        </summary>
        <div className="agent-readiness-list">
          {rows.map((row) => (
            <div className="agent-readiness-row" key={row.label}>
              <strong>{row.label}</strong>
              <span className={`agent-readiness-status readiness-${row.status}`}>
                {row.status.replaceAll("_", " ")}
              </span>
              <small>{row.detail}</small>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

function AgentList() {
  const [agents, setAgents] = useState<AgentWithState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function refresh() {
      try {
        const agentList = await getAgents();
        const rows = await Promise.all(
          agentList.map(async (agent) => ({
            agent,
            state: await getAgentState(agent.id),
          })),
        );
        if (active) {
          setAgents(rows);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load agents");
          setLoading(false);
        }
      }
    }

    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const onlineCount = agents.filter(({ agent }) => agent.status === "online").length;

  return (
    <>
      <section className="agent-page-heading">
        <div>
          <span className="agent-eyebrow">Fleet</span>
          <h1>Agents</h1>
          <p>Autonomous sensors reporting current Wi-Fi state and recent experience telemetry.</p>
        </div>
        <div className="agent-fleet-summary" aria-label="Agent fleet summary">
          <div><strong>{agents.length}</strong><span>Total</span></div>
          <div><strong>{onlineCount}</strong><span>Online</span></div>
          <div><strong>{agents.length - onlineCount}</strong><span>Offline</span></div>
        </div>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}

      <section className="agent-list-panel">
        <div className="agent-list-header">
          <div>
            <h2>Managed agents</h2>
            <p>Status is derived from heartbeat recency; Wi-Fi values come from the latest Current State.</p>
          </div>
          <span className="agent-live-indicator"><i />Auto-refresh 5s</span>
        </div>

        {loading ? (
          <div className="agent-empty">Loading agents…</div>
        ) : agents.length === 0 ? (
          <div className="agent-empty">
            <strong>No agents enrolled</strong>
            <span>Start an Agent and run <code>wifi-agent enroll</code>.</span>
          </div>
        ) : (
          <div className="managed-agent-grid">
            {agents.map(({ agent, state }) => (
              <ManagedAgentCard
                key={agent.id}
                agent={agent}
                state={state}
                stateFresh={isCurrentState(agent, state)}
                onOpen={() => navigateToAgent(agent.id)}
              />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function LinkScorePanel({ score, fresh }: { score: LinkScore | null; fresh: boolean }) {
  const visible = fresh ? score : null;
  return (
    <section className="agent-panel agent-link-score">
      <div className="agent-panel-heading">
        <div><span className="agent-eyebrow">Current link</span><h2>Wi-Fi link score</h2></div>
        <small>{visible?.version ?? "Awaiting current data"}</small>
      </div>
      <div className="agent-link-score-body">
        <div className="agent-link-score-value">
          <strong>{visible?.value == null ? "—" : visible.value.toFixed(0)}</strong>
          <span>/100</span>
          <small>{visible?.status ?? "unavailable"}</small>
        </div>
        <div className="agent-link-score-explanation">
          <p>
            Based on the current RSSI and comparable TX counter intervals.
            Metric coverage: <strong>{visible?.coverage_percent ?? 0}%</strong>.
          </p>
          {visible?.components.map((component) => (
            <div className="agent-link-score-component" key={component.metric}>
              <span>{component.label} · {component.weight_percent}% weight</span>
              <strong>{formatMetric(component.reading, component.unit)}</strong>
              <small>{component.score == null ? "No comparable reading" : `${component.score.toFixed(0)}/100`}</small>
            </div>
          ))}
          {!fresh && <p>The Agent is offline or its Current State is older than 30 seconds.</p>}
          {visible?.limitations.map((message) => <small key={message}>{message}</small>)}
        </div>
      </div>
    </section>
  );
}

function AgentDetail({ agentId }: { agentId: string }) {
  const [agent, setAgent] = useState<AgentSummary | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [state, setState] = useState<AgentCurrentState | null>(null);
  const [telemetry, setTelemetry] = useState<Record<string, TelemetryPoint[]>>({});
  const [rangeHours, setRangeHours] = useState<number>(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function refreshState() {
      try {
        const [agentData, stateData] = await Promise.all([
          getAgent(agentId),
          getAgentState(agentId),
        ]);
        if (active) {
          setAgent(agentData);
          setState(stateData);
          setError(null);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Unable to load agent");
      }
    }

    void refreshState();
    const timer = window.setInterval(() => void refreshState(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [agentId]);

  useEffect(() => {
    let active = true;

    async function refreshTelemetry() {
      try {
        const series = await Promise.all(
          TELEMETRY_METRICS.map(async ({ key }) => [
            key,
            await getAgentTelemetry(agentId, key, rangeHours),
          ] as const),
        );
        if (active) {
          setTelemetry(Object.fromEntries(series));
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Unable to load telemetry");
      }
    }

    void refreshTelemetry();
    const timer = window.setInterval(() => void refreshTelemetry(), 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [agentId, rangeHours]);

  if (!agent && !error) {
    return <div className="agent-empty">Loading agent…</div>;
  }

  if (!agent) {
    return (
      <div className="agent-error" role="alert">
        {error ?? "Agent not found"} <button type="button" onClick={navigateToAgents}>Back to agents</button>
      </div>
    );
  }

  async function saveName(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const normalized = nameInput.trim();
    if (!normalized || savingName || !agent) return;
    setSavingName(true);
    setNameError(null);
    try {
      const updated = await renameAgent(agent.id, normalized);
      setAgent(updated);
      setEditingName(false);
    } catch (err) {
      setNameError(err instanceof Error ? err.message : "Unable to rename agent");
    } finally {
      setSavingName(false);
    }
  }

  const wifi = state?.wifi;
  const network = state?.network;
  const currentStateFresh = isCurrentState(agent, state);
  const wifiPresentation = describeWifiConnection(wifi);

  return (
    <>
      <button type="button" className="agent-back" onClick={navigateToAgents}>← Agents</button>

      <section className="agent-detail-heading">
        <div>
          <div className="agent-title-line">
            <h1>{agent.name}</h1>
            <span className={`agent-status ${statusClass(agent.status)}`}>
              <i />{agent.status === "online" ? "Online" : "Offline"}
            </span>
            {!editingName && (
              <button type="button" className="agent-rename-trigger" onClick={() => {
                setNameInput(agent.name);
                setNameError(null);
                setEditingName(true);
              }}>Rename agent</button>
            )}
          </div>
          <p>{agent.hostname} · {agent.agent_type} · Agent {agent.agent_version}</p>
          {editingName && (
            <form className="agent-rename-form" onSubmit={(event) => void saveName(event)}>
              <label htmlFor="agent-display-name">Agent display name
                <input id="agent-display-name" autoFocus maxLength={128} required value={nameInput}
                  onChange={(event) => setNameInput(event.target.value)} disabled={savingName} />
              </label>
              <button type="submit" disabled={!nameInput.trim() || savingName}>
                {savingName ? "Saving…" : "Save"}
              </button>
              <button type="button" disabled={savingName} onClick={() => {
                setEditingName(false);
                setNameError(null);
              }}>Cancel</button>
            </form>
          )}
        </div>
        <div className="agent-heading-actions">
          <div className="agent-heading-meta">
            <span>Last seen</span>
            <strong>{formatRelativeTime(agent.last_seen_at)}</strong>
            <small>{formatDate(agent.last_seen_at)}</small>
          </div>
          <a className="agent-primary-action" href={diagnosticsAgentHash(agent.id)}>
            Start collection
          </a>
        </div>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}
      {nameError && <div className="agent-error" role="alert">{nameError}</div>}

      <section className="agent-current-strip" aria-label="Current wireless connection">
        <article>
          <span>Network</span>
          <strong>{wifi?.ssid ?? "—"}</strong>
          <small>{wifi?.connected === false ? "Disconnected" : wifi?.bssid ?? "No BSSID"}</small>
        </article>
        <article>
          <span>Radio</span>
          <strong>{wifiPresentation.band}</strong>
          <small>{wifiPresentation.frequency}</small>
        </article>
        <article>
          <span>Channel</span>
          <strong>{wifi?.channel ?? "—"}</strong>
          <small>{wifi?.channel_width_mhz != null ? `${wifi.channel_width_mhz} MHz width` : "Width unavailable"}</small>
        </article>
        <article>
          <span>Wi-Fi</span>
          <strong>{wifiPresentation.generation}</strong>
          <small>{wifiPresentation.ieee} · {wifiPresentation.phy}</small>
        </article>
        <article>
          <span>Signal</span>
          <strong>{formatMetric(wifi?.rssi_dbm, "dBm")}</strong>
          <small>{wifi?.snr_db != null ? `SNR ${formatMetric(wifi.snr_db, "dB")}` : "SNR unavailable"}</small>
        </article>
        <article>
          <span>TX / RX</span>
          <strong>{formatMetric(wifi?.tx_rate_mbps, "Mbps")}</strong>
          <small>RX {formatMetric(wifi?.rx_rate_mbps, "Mbps")}</small>
        </article>
      </section>

      <ExperiencePath
        state={state}
        fresh={currentStateFresh}
      />

      <LinkScorePanel
        score={state?.wifi.link_score ?? null}
        fresh={currentStateFresh}
      />

      <div className="agent-detail-grid">
        <section className="agent-panel">
          <div className="agent-panel-heading"><div><span className="agent-eyebrow">Current state</span><h2>Wi-Fi</h2></div><small>{state ? formatRelativeTime(state.observed_at) : "No state"}</small></div>
          {state ? (
            <dl className="agent-definition-list">
              <dt>Interface</dt><dd>{wifi?.interface ?? "—"}</dd>
              <dt>SSID</dt><dd>{wifi?.ssid ?? "—"}</dd>
              <dt>BSSID</dt><dd>{wifi?.bssid ?? "—"}</dd>
              <dt>Band / frequency</dt><dd>{wifiPresentation.band} · {wifiPresentation.frequency}</dd>
              <dt>Channel / width</dt><dd>{wifi?.channel ?? "—"} · {wifi?.channel_width_mhz != null ? `${wifi.channel_width_mhz} MHz` : "—"}</dd>
              <dt>Wi-Fi standard</dt><dd>{wifiPresentation.generation} · {wifiPresentation.ieee} · {wifiPresentation.shorthand}</dd>
              <dt>PHY</dt><dd>{wifiPresentation.phy}</dd>
              <dt>MCS / NSS</dt><dd>TX {wifi?.tx_mcs ?? "—"}/{wifi?.tx_nss ?? "—"} · RX {wifi?.rx_mcs ?? "—"}/{wifi?.rx_nss ?? "—"}</dd>
            </dl>
          ) : <div className="agent-empty agent-empty-compact">No Current State has been published yet.</div>}
        </section>

        <section className="agent-panel">
          <div className="agent-panel-heading"><div><span className="agent-eyebrow">Current state</span><h2>Network</h2></div></div>
          <dl className="agent-definition-list">
            <dt>IPv4</dt><dd>{network?.ipv4_address ? `${network.ipv4_address}/${network.prefix_length ?? "—"}` : "—"}</dd>
            <dt>Gateway</dt><dd>{network?.gateway ?? "—"}</dd>
            <dt>Gateway latency</dt><dd>{formatMetric(network?.gateway_latency_ms, "ms")}</dd>
            <dt>DNS latency</dt><dd>{formatMetric(network?.dns_latency_ms, "ms")}</dd>
            <dt>Internet latency</dt><dd>{formatMetric(network?.internet_latency_ms, "ms")}</dd>
          </dl>
        </section>
      </div>

      {state && state.collector_errors.length > 0 && (
        <section className="agent-warning-panel">
          <strong>Collector warnings</strong>
          <ul>{state.collector_errors.map((message) => <li key={message}>{message}</li>)}</ul>
        </section>
      )}

      <section className="agent-panel agent-telemetry-panel">
        <div className="agent-telemetry-toolbar">
          <div>
            <span className="agent-eyebrow">Rolling telemetry</span>
            <h2>Recent Wi-Fi behavior</h2>
            <p>Aggregated observations retained by the Server for short-term context.</p>
          </div>
          <div className="agent-range-selector" aria-label="Telemetry period">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option.label}
                type="button"
                className={rangeHours === option.hours ? "active" : ""}
                onClick={() => setRangeHours(option.hours)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <div className="agent-chart-grid">
          {TELEMETRY_METRICS
            .filter((metric) => metric.key !== "wifi.channel_utilization_percent"
              || (telemetry[metric.key]?.length ?? 0) > 0)
            .map((metric) => (
              <TelemetryChart
                key={metric.key}
                points={telemetry[metric.key] ?? []}
                label={metric.label}
                unit={metric.unit}
              />
            ))}
        </div>
      </section>

      <SensorReadiness
        agent={agent}
        state={state}
        fresh={isCurrentState(agent, state)}
      />

      <section className="agent-panel agent-advertised-capabilities">
        <details className="agent-capability-details">
          <summary>
            <div className="agent-capability-summary-main">
              <span className="agent-eyebrow">Agent inventory</span>
              <strong>Advertised capabilities</strong>
              <small>Enrollment prerequisites, not runtime validation</small>
            </div>
            <div className="agent-capability-summary-meta">
              <span>{agent.capabilities.length} advertised</span>
              <i aria-hidden="true">⌄</i>
            </div>
          </summary>
          <div className="agent-capability-details-body">
            <p>
              These entries describe tools and runtime prerequisites advertised when the Agent
              enrolled. Use Sensor readiness above to see what is currently verified and producing
              measurements.
            </p>
            <div className="agent-capabilities">
              {agent.capabilities.map((capability) => (
                <span key={capability.capability} className={capability.enabled ? "" : "disabled"}>
                  {capability.capability}
                </span>
              ))}
            </div>
            <div className="agent-platform-meta">
              <span><strong>OS</strong>{[agent.os_name, agent.os_version].filter(Boolean).join(" ") || "—"}</span>
              <span><strong>First seen</strong>{formatDate(agent.first_seen_at)}</span>
              <span><strong>Agent ID</strong><code>{agent.id}</code></span>
            </div>
          </div>
        </details>
      </section>
    </>
  );
}

export default function AgentWorkspace() {
  const [route, setRoute] = useState(() => parseWorkspaceRoute(window.location.hash));

  useEffect(() => {
    if (!window.location.hash) {
      window.history.replaceState(null, "", "#agents");
    }
    const handleHash = () => setRoute(parseWorkspaceRoute(window.location.hash));
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);

  return (
    <main className="agent-shell">
      <header className="agent-appbar">
        <div className="agent-brand">
          <div className="agent-brand-mark">WX</div>
          <div><strong>Wi-Fi Experience</strong><span>Network assurance</span></div>
        </div>
        <div className="agent-appbar-actions">
          <nav aria-label="Primary navigation">
            <button type="button" className={route.section === "agents" ? "active" : ""} onClick={navigateToAgents}>Agents</button>
            <button type="button" className={route.section === "diagnostics" ? "active" : ""} onClick={() => { window.location.hash = "#diagnostics"; }}>Diagnostics</button>
          </nav>
          <GlobalCollectionIndicator />
        </div>
      </header>

      <div className="agent-content">
        {route.section === "diagnostics" && route.agentId && route.recordingId ? (
          <RecordingDetail agentId={route.agentId} recordingId={route.recordingId} />
        ) : route.section === "diagnostics" ? (
          <DiagnosticsWorkspace agentId={route.agentId} />
        ) : route.agentId ? (
          <AgentDetail agentId={route.agentId} />
        ) : (
          <AgentList />
        )}
      </div>
    </main>
  );
}
