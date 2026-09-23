import type { HistoryPoint, HistoryWindow } from "./types";


export type TimelineAxis = "y" | "y2" | "y3" | "y4";


export interface TimelineMetricDefinition {
  key: string;
  label: string;
  unit: string;
  axis: TimelineAxis;
  row: "wifi" | "latency" | "loss" | "retries";
  color: string;
}


export interface TimelineSeries extends TimelineMetricDefinition {
  x: string[];
  y: Array<number | null>;
  hoverText: string[];
}


export const TIMELINE_METRICS: TimelineMetricDefinition[] = [
  {
    key: "signal_dbm",
    label: "RSSI",
    unit: "dBm",
    axis: "y",
    row: "wifi",
    color: "#175cd3",
  },
  {
    key: "gateway_latency_avg_ms",
    label: "Gateway ICMP",
    unit: "ms",
    axis: "y2",
    row: "latency",
    color: "#175cd3",
  },
  {
    key: "internet_latency_avg_ms",
    label: "External ICMP",
    unit: "ms",
    axis: "y2",
    row: "latency",
    color: "#9333ea",
  },
  {
    key: "dns_latency_ms",
    label: "DNS · host",
    unit: "ms",
    axis: "y2",
    row: "latency",
    color: "#17803d",
  },
  {
    key: "https_total_time_ms",
    label: "HTTPS · host",
    unit: "ms",
    axis: "y2",
    row: "latency",
    color: "#c05621",
  },
  {
    key: "gateway_packet_loss_percent",
    label: "Gateway loss",
    unit: "%",
    axis: "y3",
    row: "loss",
    color: "#175cd3",
  },
  {
    key: "internet_packet_loss_percent",
    label: "External loss",
    unit: "%",
    axis: "y3",
    row: "loss",
    color: "#9333ea",
  },
  {
    key: "tx_retries_per_100_packets",
    label: "TX retries",
    unit: "/ 100 TX",
    axis: "y4",
    row: "retries",
    color: "#c05621",
  },
];


function number(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}


function hoverText(
  point: HistoryPoint,
  definition: TimelineMetricDefinition,
): string {
  const metric = point.metrics[definition.key];
  const unit = definition.unit ? ` ${definition.unit}` : "";
  return [
    `<b>${definition.label}</b>`,
    new Date(point.timestamp).toLocaleString(),
    `Average: ${number(metric?.avg)}${unit}`,
    `P50: ${number(metric?.p50)}${unit}`,
    `P95: ${number(metric?.p95)}${unit}`,
    `P99: ${number(metric?.p99)}${unit}`,
    `Min / max: ${number(metric?.min)} / ${number(metric?.max)}${unit}`,
    `Available: ${metric?.count ?? 0}/${point.sample_count}`,
  ].join("<br>");
}


export function buildTimelineSeries(data: HistoryWindow): TimelineSeries[] {
  return TIMELINE_METRICS.map((definition) => ({
    ...definition,
    x: data.points.map((point) => point.timestamp),
    y: data.points.map((point) => point.metrics[definition.key]?.avg ?? null),
    hoverText: data.points.map((point) => hoverText(point, definition)),
  }));
}


export interface HistoricalOverview {
  totalSamples: number;
  bucketSeconds: number;
  environmentEvents: number;
  connectionCycles: number;
  applicationOutages: number;
}


export function historicalOverview(data: HistoryWindow): HistoricalOverview {
  return {
    totalSamples: data.total_samples,
    bucketSeconds: data.bucket_seconds,
    environmentEvents: data.events.length,
    connectionCycles: data.connection_cycles?.length ?? 0,
    applicationOutages: data.application_availability?.targets.reduce(
      (total, target) => total + target.outage_count,
      0,
    ) ?? 0,
  };
}
