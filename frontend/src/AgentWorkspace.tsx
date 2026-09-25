import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  getAgent,
  getAgents,
  getAgentState,
  getAgentTelemetry,
  renameAgent,
} from "./agentApi";
import RecordingPanel from "./RecordingPanel";
import RecordingDetail from "./RecordingDetail";
import type {
  AgentCurrentState,
  AgentSummary,
  AgentWithState,
  LinkScore,
  TelemetryPoint,
} from "./agentTypes";
import "./AgentWorkspace.css";

const TELEMETRY_METRICS = [
  { key: "wifi.rssi_dbm", label: "RSSI", unit: "dBm" },
  { key: "wifi.snr_db", label: "SNR", unit: "dB" },
  { key: "wifi.tx_rate_mbps", label: "TX rate", unit: "Mbps" },
  { key: "wifi.rx_rate_mbps", label: "RX rate", unit: "Mbps" },
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

interface WorkspaceRoute {
  agentId: string | null;
  recordingId: string | null;
}

function routeFromHash(): WorkspaceRoute {
  const recordingMatch = window.location.hash.match(
    /^#agents\/([^/]+)\/recordings\/([^/]+)$/,
  );
  if (recordingMatch) {
    return {
      agentId: decodeURIComponent(recordingMatch[1]),
      recordingId: decodeURIComponent(recordingMatch[2]),
    };
  }
  const agentMatch = window.location.hash.match(/^#agents\/([^/]+)$/);
  return {
    agentId: agentMatch ? decodeURIComponent(agentMatch[1]) : null,
    recordingId: null,
  };
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
          <div className="agent-table-wrap">
            <table className="agent-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Wi-Fi</th>
                  <th>Signal</th>
                  <th>Link score</th>
                  <th>Channel</th>
                  <th>Last seen</th>
                  <th aria-label="Open agent" />
                </tr>
              </thead>
              <tbody>
                {agents.map(({ agent, state }) => (
                  <tr key={agent.id}>
                    <td>
                      <button type="button" className="agent-name-link" onClick={() => navigateToAgent(agent.id)}>{agent.name}</button>
                      <small>{agent.hostname}</small>
                    </td>
                    <td>
                      <span className={`agent-status ${statusClass(agent.status)}`}>
                        <i />{agent.status === "online" ? "Online" : "Offline"}
                      </span>
                    </td>
                    <td>
                      <strong>{state?.wifi.ssid ?? "—"}</strong>
                      <small>{state?.wifi.bssid ?? "No current state"}</small>
                    </td>
                    <td>{formatMetric(state?.wifi.rssi_dbm, "dBm")}</td>
                    <td>
                      {isCurrentState(agent, state) && state?.wifi.link_score?.value != null
                        ? `${state.wifi.link_score.value.toFixed(0)}/100`
                        : "—"}
                      <small>{isCurrentState(agent, state)
                        ? state?.wifi.link_score?.status ?? "Unavailable"
                        : "No current score"}</small>
                    </td>
                    <td>{state?.wifi.channel ?? "—"}</td>
                    <td>
                      <strong>{formatRelativeTime(agent.last_seen_at)}</strong>
                      <small>{formatDate(agent.last_seen_at)}</small>
                    </td>
                    <td><button type="button" className="agent-row-action" aria-label={`Open ${agent.name}`} onClick={() => navigateToAgent(agent.id)}>→</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
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
        <div className="agent-heading-meta">
          <span>Last seen</span>
          <strong>{formatRelativeTime(agent.last_seen_at)}</strong>
          <small>{formatDate(agent.last_seen_at)}</small>
        </div>
      </section>

      {error && <div className="agent-error" role="alert">{error}</div>}
      {nameError && <div className="agent-error" role="alert">{nameError}</div>}

      <section className="agent-current-strip" aria-label="Current Wi-Fi summary">
        <article><span>SSID</span><strong>{wifi?.ssid ?? "—"}</strong><small>{wifi?.connected === false ? "Disconnected" : wifi?.bssid ?? "No BSSID"}</small></article>
        <article><span>RSSI</span><strong>{formatMetric(wifi?.rssi_dbm, "dBm")}</strong><small>Current signal</small></article>
        <article><span>SNR</span><strong>{formatMetric(wifi?.snr_db, "dB")}</strong><small>{wifi?.noise_dbm != null ? `Noise ${formatMetric(wifi.noise_dbm, "dBm")}` : "Noise unavailable"}</small></article>
        <article><span>Channel</span><strong>{wifi?.channel ?? "—"}</strong><small>{wifi?.frequency_mhz ? `${wifi.frequency_mhz} MHz · ${wifi.channel_width_mhz ?? "—"} MHz` : "Frequency unavailable"}</small></article>
        <article><span>TX / RX</span><strong>{formatMetric(wifi?.tx_rate_mbps, "Mbps")}</strong><small>RX {formatMetric(wifi?.rx_rate_mbps, "Mbps")}</small></article>
      </section>

      <LinkScorePanel
        score={state?.wifi.link_score ?? null}
        fresh={isCurrentState(agent, state)}
      />

      <RecordingPanel agent={agent} />

      <div className="agent-detail-grid">
        <section className="agent-panel">
          <div className="agent-panel-heading"><div><span className="agent-eyebrow">Current state</span><h2>Wi-Fi</h2></div><small>{state ? formatRelativeTime(state.observed_at) : "No state"}</small></div>
          {state ? (
            <dl className="agent-definition-list">
              <dt>Interface</dt><dd>{wifi?.interface ?? "—"}</dd>
              <dt>SSID</dt><dd>{wifi?.ssid ?? "—"}</dd>
              <dt>BSSID</dt><dd>{wifi?.bssid ?? "—"}</dd>
              <dt>Radio</dt><dd>{wifi?.frequency_mhz ? `${wifi.frequency_mhz} MHz · ch ${wifi.channel ?? "—"} · ${wifi.channel_width_mhz ?? "—"} MHz` : "—"}</dd>
              <dt>PHY</dt><dd>TX {wifi?.tx_phy ?? "—"} / RX {wifi?.rx_phy ?? "—"}</dd>
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
          {TELEMETRY_METRICS.map((metric) => (
            <TelemetryChart
              key={metric.key}
              points={telemetry[metric.key] ?? []}
              label={metric.label}
              unit={metric.unit}
            />
          ))}
        </div>
      </section>

      <section className="agent-panel">
        <div className="agent-panel-heading">
          <div><span className="agent-eyebrow">Agent</span><h2>Capabilities</h2></div>
          <small>{agent.capabilities.filter((capability) => capability.enabled).length} enabled</small>
        </div>
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
      </section>
    </>
  );
}

export default function AgentWorkspace() {
  const [route, setRoute] = useState<WorkspaceRoute>(() => routeFromHash());

  useEffect(() => {
    if (!window.location.hash) {
      window.history.replaceState(null, "", "#agents");
    }
    const handleHash = () => setRoute(routeFromHash());
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
        <nav aria-label="Primary navigation">
          <button type="button" className="active" onClick={navigateToAgents}>Agents</button>
        </nav>
      </header>

      <div className="agent-content">
        {route.agentId && route.recordingId ? (
          <RecordingDetail agentId={route.agentId} recordingId={route.recordingId} />
        ) : route.agentId ? (
          <AgentDetail agentId={route.agentId} />
        ) : (
          <AgentList />
        )}
      </div>
    </main>
  );
}
