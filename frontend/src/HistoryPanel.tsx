import { Component, lazy, Suspense, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getHistoryInterfaces, getHistoryWindow, getReportUrl } from "./api";
import { buildTimelineEvents } from "./historyEventsModel";
import type { HistoryWindow } from "./types";

const HistoricalTimeline = lazy(() => import("./HistoricalTimeline"));

class HistoricalChartBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return <div className="empty-state" role="alert">
      The historical chart could not be displayed. The measurements and comparisons below are still available.
      <button type="button" onClick={() => this.setState({ failed: false })}>Retry chart</button>
    </div>;
    return this.props.children;
  }
}

const format = (value: number | null | undefined) => value == null
  ? "Unavailable" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const date = (value: string) => new Date(value).toLocaleString();
const formatAvailability = (value: number | null | undefined) => value == null
  ? "Unavailable" : `${format(value)}%`;
const formatDuration = (seconds: number | null | undefined) => {
  if (seconds == null || !Number.isFinite(seconds)) return "Unavailable";
  if (seconds < 60) return `${format(seconds)} s`;
  if (seconds < 3600) return `${format(seconds / 60)} min`;
  return `${format(seconds / 3600)} h`;
};
const comparisonMetrics = [
  { key: "signal_dbm", label: "RSSI", unit: "dBm", higherIsBetter: true },
  { key: "gateway_latency_avg_ms", label: "Gateway latency", unit: "ms", higherIsBetter: false },
  { key: "internet_latency_avg_ms", label: "Internet latency", unit: "ms", higherIsBetter: false },
  { key: "gateway_packet_loss_percent", label: "Gateway packet loss", unit: "%", higherIsBetter: false },
  { key: "internet_packet_loss_percent", label: "Internet packet loss", unit: "%", higherIsBetter: false },
  { key: "tx_retries_per_100_packets", label: "TX retries", unit: "/ 100 TX", higherIsBetter: false },
];

export default function HistoryPanel({ currentInterface }: { currentInterface?: string | null }) {
  const [interfaces, setInterfaces] = useState<string[]>([]);
  const [selectedInterface, setSelectedInterface] = useState("");
  const [period, setPeriod] = useState("3600");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [customRange, setCustomRange] = useState<{ start: string; end: string } | null>(null);
  const [auto, setAuto] = useState(true);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<HistoryWindow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHistoryInterfaces().then(items => {
      if (cancelled) return;
      const options = [...new Set([...items, ...(currentInterface ? [currentInterface] : [])])].sort();
      setInterfaces(options);
      setSelectedInterface(old => old || currentInterface || options[0] || "");
    }).catch(err => { if (!cancelled) setError(String(err)); });
    return () => { cancelled = true; };
  }, [currentInterface, revision]);

  useEffect(() => {
    if (!selectedInterface || (period === "custom" && !customRange)) {
      setData(null); setLoading(false); return;
    }
    const controller = new AbortController();
    let cancelled = false;
    let busy = false;
    setData(null);
    async function refresh() {
      if (busy) return;
      busy = true;
      setLoading(true);
      const end = new Date();
      const range = period === "custom" && customRange ? customRange : {
        start: new Date(end.getTime() - Number(period) * 1000).toISOString(), end: end.toISOString(),
      };
      try {
        const history = await getHistoryWindow(selectedInterface, range.start, range.end, controller.signal);
        if (!cancelled) {
          setData(history);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) { setError(err instanceof Error ? err.message : "Unable to load history."); setData(null); }
      } finally {
        busy = false;
        if (!cancelled) setLoading(false);
      }
    }
    void refresh();
    const timer = auto && period !== "custom" ? window.setInterval(() => void refresh(), 30000) : undefined;
    return () => { cancelled = true; controller.abort(); if (timer !== undefined) window.clearInterval(timer); };
  }, [selectedInterface, period, customRange, auto, revision]);

  function applyRange() {
    const start = new Date(customStart), end = new Date(customEnd);
    const seconds = (end.getTime() - start.getTime()) / 1000;
    if (!Number.isFinite(seconds) || seconds < 1 || seconds > 604800) {
      setRangeError("Choose a start and end with a positive range of at most seven days."); return;
    }
    setRangeError(null);
    setCustomRange({ start: start.toISOString(), end: end.toISOString() });
  }

  return <section className="panel history-panel" aria-labelledby="history-title">
    <h2 id="history-title">Historical explorer</h2>
    <div className="history-controls">
      <label>Interface<select value={selectedInterface} onChange={event => setSelectedInterface(event.target.value)}>
        <option value="">Select an interface</option>
        {interfaces.map(item => <option key={item}>{item}</option>)}
      </select></label>
      <label>Period<select value={period} onChange={event => { setPeriod(event.target.value); setRangeError(null); }}>
        <option value="900">Last 15 minutes</option><option value="3600">Last hour</option>
        <option value="21600">Last 6 hours</option><option value="86400">Last 24 hours</option>
        <option value="604800">Last 7 days</option><option value="custom">Custom range</option>
      </select></label>
      <label className="history-auto"><input type="checkbox" checked={auto} disabled={period === "custom"}
        onChange={event => setAuto(event.target.checked)} /> Refresh every 30 seconds</label>
      <button type="button" onClick={() => setRevision(value => value + 1)} disabled={loading}>Refresh</button>
      {data && <button type="button" onClick={() => window.open(
        getReportUrl(selectedInterface, data.start, data.end), "_blank", "noopener,noreferrer")}>Open HTML report</button>}
    </div>
    {period === "custom" && <div className="history-controls">
      <label>Start · local time<input type="datetime-local" value={customStart} onChange={event => setCustomStart(event.target.value)} /></label>
      <label>End · local time<input type="datetime-local" value={customEnd} onChange={event => setCustomEnd(event.target.value)} /></label>
      <button type="button" onClick={applyRange}>Apply range</button>
    </div>}
    {(error || rangeError) && <p className="error" role="alert">{rangeError || error}</p>}
    {loading && <p role="status">Loading historical measurements…</p>}
    {!selectedInterface && <p>Select an interface with stored history. Monitoring can remain stopped.</p>}
    {data && <>
      <p className="metric-note">{data.total_samples.toLocaleString()} samples · buckets of {data.bucket_seconds} seconds ·
        {" "}{date(data.start)} – {date(data.end)} · timezone {Intl.DateTimeFormat().resolvedOptions().timeZone}.</p>
      <p className="metric-note">Timeline lines show averages of available readings per bucket. Empty buckets
        remain gaps, not zeros. Samples from different interfaces are never combined. DNS/HTTPS use the host route;
        retry ratios can exceed 100.</p>
      {(data.total_samples > 0 || buildTimelineEvents(data, [], []).some((event) =>
        event.kind === "connection" || event.kind === "roam" || event.kind === "environment")) &&
        <HistoricalChartBoundary key={`${selectedInterface}-${period}`}>
          <Suspense fallback={<p role="status">Preparing historical charts…</p>}>
            <HistoricalTimeline data={data} />
          </Suspense>
        </HistoricalChartBoundary>}
      {data.service_slo_summary && Object.values(data.service_slo_summary).some(
        service => service.attempt_count > 0,
      ) && <section aria-labelledby="service-slo-history-title">
        <h3 id="service-slo-history-title">Synthetic service SLA/SLO observations</h3>
        <p className="metric-note">
          Availability uses fresh definitive passed/failed executions in this selected period.
          Collection errors are excluded from the availability denominator. Historical percentiles
          are observations for the selected period; rolling incident compliance uses the profile-pinned
          runtime SLO window.
        </p>
        <div className="table-wrapper"><table>
          <thead><tr><th>Service</th><th>Availability</th><th>Success / Failure / Error</th>
            <th>Latency P95</th><th>Latency P99</th><th>Packet-loss P95</th></tr></thead>
          <tbody>{Object.entries(data.service_slo_summary).filter(([, service]) =>
            service.attempt_count > 0).map(([name, service]) => <tr key={name}>
            <td>{name.toUpperCase()}</td>
            <td>{format(service.availability_percent)}%</td>
            <td>{service.success_count} / {service.failure_count} /
              {" "}{service.measurement_error_count}</td>
            <td>{format(service.latency_ms.p95)} ms</td>
            <td>{format(service.latency_ms.p99)} ms</td>
            <td>{service.packet_loss_percent.count > 0
              ? `${format(service.packet_loss_percent.p95)}%` : "Not applicable / unavailable"}</td>
          </tr>)}</tbody>
        </table></div>
      </section>}
      {data.application_availability && data.application_availability.targets.some(
        target => target.attempt_count > 0,
      ) && <section aria-labelledby="application-availability-title">
        <h3 id="application-availability-title">Application availability &amp; outage accounting</h3>
        <p className="metric-note">
          Availability is execution-based: fresh passed / (passed + failed). Collection errors,
          skipped/disabled probes and cached results do not enter the denominator. An observed outage
          starts at the first fresh failed probe and ends at the first later fresh passed probe.
          Open outage duration is bounded by the selected window end; these intervals reflect probe
          observations, not exact packet-level outage boundaries.
        </p>
        <div className="table-wrapper"><table>
          <thead><tr><th>Target</th><th>Availability</th><th>Success / Failure / Error</th>
            <th>Outages</th><th>Observed outage</th><th>Longest outage</th><th>State</th></tr></thead>
          <tbody>{data.application_availability.targets.filter(target =>
            target.attempt_count > 0).map(target => <tr key={target.identity}>
            <td><strong>{target.name}</strong><br /><small>{target.kind.toUpperCase()} ·
              {" "}{target.target}{target.port !== null ? `:${target.port}` : ""}</small></td>
            <td>{formatAvailability(target.availability_percent)}</td>
            <td>{target.success_count} / {target.failure_count} /
              {" "}{target.measurement_error_count}</td>
            <td>{target.outage_count}</td>
            <td>{formatDuration(target.observed_outage_seconds)}</td>
            <td>{formatDuration(target.longest_observed_outage_seconds)}</td>
            <td>{target.open_outage ? "OPEN · recovery not observed" : "No open outage"}</td>
          </tr>)}</tbody>
        </table></div>
        {data.application_availability.targets.some(target => target.outages.length > 0) && <>
          <h4>Observed outage intervals</h4>
          <div className="table-wrapper"><table>
            <thead><tr><th>Target</th><th>Started</th><th>Last failed probe</th>
              <th>Recovery observation</th><th>Observed duration</th><th>Failed probes</th></tr></thead>
            <tbody>{data.application_availability.targets.flatMap(target =>
              target.outages.map(outage => <tr key={`${target.identity}-${outage.started_at}`}>
                <td>{target.name}</td>
                <td>{date(outage.started_at)}</td>
                <td>{date(outage.last_failed_at)}</td>
                <td>{outage.ended_at ? date(outage.ended_at) : "Not observed in selected window"}</td>
                <td>{formatDuration(outage.duration_seconds)}</td>
                <td>{outage.failure_count}</td>
              </tr>))}</tbody>
          </table></div>
        </>}
      </section>}
      {data.connection_cycle_summary && data.connection_cycle_summary.total_cycles > 0 && <section
        aria-labelledby="connection-cycle-summary-title">
        <h3 id="connection-cycle-summary-title">Connection cycle statistics</h3>
        <p className="metric-note">Percentiles use only cycles with an observed duration. Missing timing remains
          unavailable and is never converted to zero. D-Bus and sampling sources remain distinguishable.</p>
        <div className="history-comparison-grid">
          <article className="history-comparison-card"><span>Cycles</span>
            <strong>{data.connection_cycle_summary.total_cycles}</strong>
            <small>{data.connection_cycle_summary.ready_cycles} reached network ready</small></article>
          <article className="history-comparison-card"><span>Measured durations</span>
            <strong>{data.connection_cycle_summary.measurable_cycles}</strong>
            <small>{data.connection_cycle_summary.unmeasured_cycles} with unknown duration</small></article>
          <article className="history-comparison-card"><span>Ready time · P50</span>
            <strong>{format(data.connection_cycle_summary.total_time_ms.p50)} ms</strong>
            <small>Median of measured connection cycles</small></article>
          <article className="history-comparison-card"><span>Ready time · P95</span>
            <strong>{format(data.connection_cycle_summary.total_time_ms.p95)} ms</strong>
            <small>Tail connection experience</small></article>
          <article className="history-comparison-card"><span>Ready time · P99</span>
            <strong>{format(data.connection_cycle_summary.total_time_ms.p99)} ms</strong>
            <small>Extreme measured tail</small></article>
        </div>
        <div className="table-wrapper"><table>
          <thead><tr><th>Stage</th><th>Samples</th><th>P50</th><th>P95</th><th>P99</th><th>Sources</th></tr></thead>
          <tbody>{Object.entries(data.connection_cycle_summary.stages).map(([key, stats]) => <tr key={key}>
            <td>{key.replaceAll("_", " ")}</td><td>{stats.count}</td>
            <td>{format(stats.p50)} ms</td><td>{format(stats.p95)} ms</td><td>{format(stats.p99)} ms</td>
            <td>{Object.entries(stats.sources ?? {}).map(([source, count]) =>
              `${source.replaceAll("_", " ")}: ${count}`).join(" · ") || "Unavailable"}</td>
          </tr>)}</tbody>
        </table></div>
      </section>}
      {(data.connection_cycles?.length ?? 0) > 0 && <section aria-labelledby="connection-cycle-history-title">
        <h3 id="connection-cycle-history-title">Connection cycles</h3>
        <p className="metric-note">Sampling-derived durations are upper-bound estimates. Event-derived stages
          retain their NetworkManager D-Bus source. Sessions already active when monitoring starts keep unknown timing.</p>
        <div className="table-wrapper"><table>
          <thead><tr><th>Type</th><th>State</th><th>SSID / BSSID</th><th>Started</th><th>Ready estimate</th><th>Resolution</th></tr></thead>
          <tbody>{data.connection_cycles?.map(cycle => <tr key={cycle.session_id}>
            <td>{cycle.session_type.replaceAll("_", " ")}</td><td>{cycle.state}</td>
            <td>{cycle.ssid ?? "Unavailable"}<br /><small>{cycle.bssid ?? "Unavailable"}</small></td>
            <td>{cycle.started_at ? date(cycle.started_at) : "Not observed"}</td>
            <td>{cycle.total_time_ms == null ? "Unknown" : `${format(cycle.total_time_ms)} ms`}</td>
            <td>{cycle.sample_resolution_ms == null ? "Unknown" : `${format(cycle.sample_resolution_ms)} ms`}</td>
          </tr>)}</tbody>
        </table></div>
      </section>}
      {data.comparison && <section className="history-comparison" aria-labelledby="history-comparison-title">
        <h3 id="history-comparison-title">Compared with the previous equivalent period</h3>
        <p className="metric-note">Previous period: {date(data.comparison.previous_start)} – {date(data.comparison.previous_end)}.
          Values use all available readings; unavailable metrics remain unavailable.</p>
        {data.comparison.connection_cycles && <div className="history-comparison-grid">
          {(() => {
            const current = data.comparison?.connection_cycles?.current.total_time_ms.p95;
            const previous = data.comparison?.connection_cycles?.previous.total_time_ms.p95;
            const delta = current != null && previous != null ? current - previous : null;
            const trend = delta == null || Math.abs(delta) < 0.005 ? "flat" : delta < 0 ? "improved" : "worse";
            return <article className={`history-comparison-card trend-${trend}`}>
              <span>Connection ready time · P95</span><strong>{format(current)} ms</strong>
              <small>{delta == null ? "No comparable measured cycles" :
                `${delta >= 0 ? "+" : ""}${format(delta)} ms vs previous`}</small>
              <em>{trend === "improved" ? "Improved" : trend === "worse" ? "Worse" : "Stable / unavailable"}</em>
            </article>;
          })()}
        </div>}
        {data.comparison.application_availability &&
          data.comparison.application_availability.current.targets.length > 0 && <div className="table-wrapper">
          <h4>Application availability compared with previous period</h4>
          <table>
            <thead><tr><th>Target</th><th>Current</th><th>Previous</th><th>Delta</th></tr></thead>
            <tbody>{data.comparison.application_availability.current.targets.map(target => {
              const previous = data.comparison?.application_availability?.previous.targets.find(
                item => item.identity === target.identity,
              );
              const currentValue = target.availability_percent;
              const previousValue = previous?.availability_percent ?? null;
              const delta = currentValue !== null && previousValue !== null
                ? currentValue - previousValue : null;
              return <tr key={target.identity}>
                <td>{target.name}<br /><small>{target.target}</small></td>
                <td>{formatAvailability(currentValue)}</td>
                <td>{formatAvailability(previousValue)}</td>
                <td>{delta === null ? "Unavailable" :
                  `${delta >= 0 ? "+" : ""}${format(delta)} pp`}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>}
        <div className="history-comparison-grid">
          {comparisonMetrics.map(item => {
            const current = data.comparison?.current.metrics[item.key]?.avg;
            const previous = data.comparison?.previous.metrics[item.key]?.avg;
            const delta = current != null && previous != null ? current - previous : null;
            const trend = delta == null || Math.abs(delta) < 0.005 ? "flat" :
              ((item.higherIsBetter && delta > 0) || (!item.higherIsBetter && delta < 0) ? "improved" : "worse");
            return <article key={item.key} className={`history-comparison-card trend-${trend}`}>
              <span>{item.label}</span>
              <strong>{format(current)} {item.unit}</strong>
              <small>{delta == null ? "No comparable readings" : `${delta >= 0 ? "+" : ""}${format(delta)} ${item.unit} vs previous`}</small>
              <em>{trend === "improved" ? "Improved" : trend === "worse" ? "Worse" : "Stable / unavailable"}</em>
            </article>;
          })}
        </div>
      </section>}
      {data.total_samples === 0 && <div className="empty-state">
        No samples for this interface and period.
      </div>}
    </>}
  </section>;
}
