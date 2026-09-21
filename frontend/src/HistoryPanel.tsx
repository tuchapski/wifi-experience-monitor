import { useEffect, useState } from "react";
import { getHistoryInterfaces, getHistoryWindow } from "./api";
import type { EnvironmentChange, HistoryWindow } from "./types";

interface Series { key: string; label: string; color: string }
const groups: { title: string; unit: string; series: Series[] }[] = [
  { title: "Wi-Fi signal", unit: "dBm", series: [
    { key: "signal_dbm", label: "RSSI", color: "#175cd3" },
  ] },
  { title: "Latency and response time", unit: "ms", series: [
    { key: "gateway_latency_avg_ms", label: "Gateway ICMP", color: "#175cd3" },
    { key: "internet_latency_avg_ms", label: "External ICMP", color: "#9333ea" },
    { key: "dns_latency_ms", label: "DNS · host", color: "#17803d" },
    { key: "https_total_time_ms", label: "HTTPS · host", color: "#c05621" },
  ] },
  { title: "ICMP packet loss", unit: "%", series: [
    { key: "gateway_packet_loss_percent", label: "Gateway", color: "#175cd3" },
    { key: "internet_packet_loss_percent", label: "External target", color: "#9333ea" },
  ] },
  { title: "Wi-Fi retries", unit: "retries / 100 TX packets", series: [
    { key: "tx_retries_per_100_packets", label: "TX retries", color: "#c05621" },
  ] },
];
const format = (value: number | null | undefined) => value == null
  ? "Unavailable" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const date = (value: string) => new Date(value).toLocaleString();

function HistoryChart({ data, title, unit, series }: { data: HistoryWindow; title: string; unit: string; series: Series[] }) {
  const [hidden, setHidden] = useState<string[]>([]);
  const [cursor, setCursor] = useState(0);
  const visible = series.filter(item => !hidden.includes(item.key));
  const values = data.points.flatMap(point => visible.flatMap(item => {
    const value = point.metrics[item.key]?.avg;
    return value == null ? [] : [value];
  }));
  const hasValues = values.length > 0;
  let low = hasValues ? Math.min(...values) : 0;
  let high = hasValues ? Math.max(...values) : 1;
  if (high === low) { low -= 1; high += 1; }
  const padding = (high - low) * 0.1;
  low -= padding; high += padding;
  const x = (index: number) => 62 + index * 710 / Math.max(1, data.points.length - 1);
  const y = (value: number) => 175 - (value - low) * 145 / (high - low);
  const selected = Math.min(cursor, data.points.length - 1);
  const point = data.points[selected];
  const chartStart = new Date(data.start).getTime();
  const chartEnd = new Date(data.end).getTime();
  const eventPosition = (event: EnvironmentChange) => {
    const timestamp = event.timestamp ? new Date(event.timestamp).getTime() : chartStart;
    return 62 + Math.max(0, Math.min(1, (timestamp - chartStart) / Math.max(1, chartEnd - chartStart))) * 710;
  };
  function segments(key: string): string[] {
    const result: string[] = [];
    let segment: string[] = [];
    data.points.forEach((item, index) => {
      const value = item.metrics[key]?.avg;
      if (value == null) {
        if (segment.length) result.push(segment.join(" "));
        segment = [];
      } else segment.push(`${x(index)},${y(value)}`);
    });
    if (segment.length) result.push(segment.join(" "));
    return result;
  }
  return <section className="history-chart">
    <h3>{title}</h3>
    <div className="history-legend" aria-label={`${title} series`}>
      {series.map(item => <label key={item.key} style={{ borderColor: item.color }}>
        <input type="checkbox" checked={!hidden.includes(item.key)} onChange={() => setHidden(old =>
          old.includes(item.key) ? old.filter(key => key !== item.key) : [...old, item.key])} />
        {item.label}
      </label>)}
    </div>
    <svg viewBox="0 0 800 220" role="img" aria-label={`${title}, averages in ${unit}`}
      onPointerMove={event => {
        const rect = event.currentTarget.getBoundingClientRect();
        const position = ((event.clientX - rect.left) / rect.width * 800 - 62) / 710;
        setCursor(Math.max(0, Math.min(data.points.length - 1, Math.round(position * (data.points.length - 1)))));
      }}>
      {[0, 0.5, 1].map(fraction => {
        const value = low + fraction * (high - low);
        return <g key={fraction}><line x1="62" x2="772" y1={y(value)} y2={y(value)} stroke="#e4e7ec" />
          <text x="55" y={y(value) + 4} textAnchor="end">{format(value)}</text></g>;
      })}
      <text x="62" y="16">{unit}</text>
      {visible.map(item => <g key={item.key}>
        {segments(item.key).map((points, index) => <polyline key={index} points={points}
          fill="none" stroke={item.color} strokeWidth="2" />)}
        {data.points.map((entry, index) => entry.metrics[item.key]?.avg == null ? null :
          <circle key={index} cx={x(index)} cy={y(entry.metrics[item.key].avg!)} r="1.6" fill={item.color} />)}
      </g>)}
      {data.events.map((event, index) => <g key={`${event.code}-${event.timestamp}-${index}`}>
        <line x1={eventPosition(event)} x2={eventPosition(event)} y1="25" y2="175"
          stroke="#b42318" strokeDasharray="3 3" />
        <title>{event.message}</title>
      </g>)}
      {point && <line x1={x(selected)} x2={x(selected)} y1="25" y2="175" stroke="#667085" strokeDasharray="4 4" />}
      {!hasValues && <text x="420" y="100" textAnchor="middle">No available values for selected series</text>}
      <text x="62" y="208">{date(data.start)}</text>
      <text x="772" y="208" textAnchor="end">{date(data.end)}</text>
    </svg>
    <label className="history-inspector">Inspect time bucket
      <input type="range" min="0" max={Math.max(0, data.points.length - 1)} value={selected}
        onChange={event => setCursor(Number(event.target.value))} />
    </label>
    {point && <div className="history-inspection">
      <strong>{date(point.timestamp)}</strong> · {point.sample_count} stored samples
      <ul>{visible.map(item => {
        const metric = point.metrics[item.key];
        return <li key={item.key}>{item.label}: average <strong>{format(metric?.avg)}</strong>,
          min {format(metric?.min)}, max {format(metric?.max)} {unit}
          {" · "}{metric?.count ?? 0}/{point.sample_count} available readings</li>;
      })}</ul>
    </div>}
    {data.events.length > 0 && <ul className="history-events">
      {data.events.map((event, index) => <li key={`${event.code}-${event.timestamp}-${index}`}>
        <time>{event.timestamp ? date(event.timestamp) : "Unknown time"}</time>{" · "}
        <strong>{event.field}</strong>{" — "}{event.message}
      </li>)}
    </ul>}
  </section>;
}

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
        const result = await getHistoryWindow(selectedInterface, range.start, range.end, controller.signal);
        if (!cancelled) { setData(result); setError(null); }
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
    <h2 id="history-title">Historical comparison</h2>
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
      <p className="metric-note">Lines show averages of available readings per bucket. Hover or use the time slider
        to inspect min/max and available counts. Empty buckets are gaps, not zeros. Samples from different interfaces
        are never combined. DNS/HTTPS use the host route; retry ratios can exceed 100.</p>
      {data.total_samples === 0 ? <div className="empty-state">No samples for this interface and period.</div> :
        <div className="history-chart-grid">{groups.map(group => <HistoryChart key={group.title} data={data} {...group} />)}</div>}
    </>}
  </section>;
}
