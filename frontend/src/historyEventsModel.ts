import type { ExperienceEpisode, HistoryWindow, IncidentRecord } from "./types";

export type EventKind = "episode" | "incident" | "outage" | "connection" | "roam" | "environment";

export interface TimelineEvent {
  id: string;
  kind: EventKind;
  start: string;
  end: string | null;
  recordedStart: string;
  recordedEnd: string | null;
  label: string;
  detail: string;
  scope: "sensor" | "interface" | "window";
}

export const EVENT_LANES: Array<{
  kind: EventKind;
  label: string;
  color: string;
  symbol: "square" | "circle" | "diamond" | "triangle-up";
  lane: number;
}> = [
  { kind: "episode", label: "Episodes", color: "#6941c6", symbol: "square", lane: 5 },
  { kind: "incident", label: "Incidents", color: "#b42318", symbol: "circle", lane: 4 },
  { kind: "outage", label: "App outages", color: "#c05621", symbol: "square", lane: 3 },
  { kind: "connection", label: "Connection cycles", color: "#175cd3", symbol: "circle", lane: 2 },
  { kind: "roam", label: "BSSID changes", color: "#00857a", symbol: "diamond", lane: 1 },
  { kind: "environment", label: "Other changes", color: "#667085", symbol: "triangle-up", lane: 0 },
];

function time(value: string | null | undefined): number {
  return value ? Date.parse(value) : Number.NaN;
}

function overlap(start: string | null | undefined, end: string | null | undefined, from: number, to: number): boolean {
  const first = time(start);
  const last = end == null ? to : time(end);
  return Number.isFinite(first) && Number.isFinite(last) && first <= to && last >= from && last >= first;
}

function bounded(start: string, end: string | null, from: number, to: number): Pick<TimelineEvent, "start" | "end"> {
  return {
    start: new Date(Math.max(from, time(start))).toISOString(),
    end: end == null ? new Date(to).toISOString() : new Date(Math.min(to, time(end))).toISOString(),
  };
}

function point(timestamp: string | undefined, from: number, to: number): boolean {
  const value = time(timestamp);
  return Number.isFinite(value) && value >= from && value <= to;
}

export function buildTimelineEvents(
  data: HistoryWindow,
  incidents: IncidentRecord[],
  episodes: ExperienceEpisode[],
): TimelineEvent[] {
  const from = time(data.start);
  const to = time(data.end);
  if (!Number.isFinite(from) || !Number.isFinite(to) || from >= to) return [];

  const events: TimelineEvent[] = [];

  for (const episode of episodes) {
    if (!overlap(episode.started_at, episode.ended_at, from, to)) continue;
    events.push({
      id: `episode:${episode.episode_id}`, kind: "episode",
      ...bounded(episode.started_at, episode.ended_at, from, to),
      recordedStart: episode.started_at, recordedEnd: episode.ended_at,
      label: `Experience episode · ${episode.severity}`,
      detail: `${episode.incident_count} incidents · ${episode.primary_domain ?? episode.correlation_status}${episode.ended_at ? "" : " · ongoing"}`,
      scope: "sensor",
    });
  }

  for (const incident of incidents) {
    if (!overlap(incident.started_at, incident.ended_at, from, to)) continue;
    events.push({
      id: `incident:${incident.id}`, kind: "incident",
      ...bounded(incident.started_at, incident.ended_at, from, to),
      recordedStart: incident.started_at, recordedEnd: incident.ended_at,
      label: `${incident.code} · ${incident.severity}`,
      detail: `${incident.message}${incident.ended_at ? "" : " · ongoing"}`,
      scope: "sensor",
    });
  }

  for (const target of data.application_availability?.targets ?? []) {
    target.outages.forEach((outage, index) => {
      if (!overlap(outage.started_at, outage.ended_at, from, to)) return;
      events.push({
        id: `outage:${target.identity}:${index}`, kind: "outage",
        ...bounded(outage.started_at, outage.ended_at, from, to),
        recordedStart: outage.started_at, recordedEnd: outage.ended_at,
        label: `${target.name} · ${target.kind.toUpperCase()}`,
        detail: `${outage.failure_count} failed probes${outage.recovered ? " · recovery observed" : " · recovery not observed"}`,
        scope: "window",
      });
    });
  }

  for (const cycle of data.connection_cycles ?? []) {
    const observedEnd = cycle.completed_at ?? cycle.last_observed_at;
    if (!cycle.started_at || !overlap(cycle.started_at, observedEnd, from, to)) continue;
    events.push({
      id: `cycle:${cycle.session_id}`, kind: "connection",
      ...bounded(cycle.started_at, observedEnd, from, to),
      recordedStart: cycle.started_at, recordedEnd: observedEnd,
      label: `${cycle.session_type.replaceAll("_", " ")} · ${cycle.state}`,
      detail: `${cycle.ssid ?? "Unknown SSID"} · ${cycle.bssid ?? "Unknown BSSID"}${cycle.total_time_ms == null ? " · duration unavailable" : ` · ${cycle.total_time_ms} ms`}`,
      scope: "interface",
    });
  }

  data.events.forEach((change, index) => {
    if (!point(change.timestamp, from, to)) return;
    const roam = change.field.toLowerCase() === "bssid" || change.code.toLowerCase().includes("bssid");
    events.push({
      id: `change:${index}:${change.timestamp}`, kind: roam ? "roam" : "environment",
      start: change.timestamp!, end: null,
      recordedStart: change.timestamp!, recordedEnd: null,
      label: change.code,
      detail: change.message,
      scope: "interface",
    });
  });

  return events.sort((a, b) => time(a.start) - time(b.start));
}

export function buildWifiIncidentEvents(data: HistoryWindow, incidents: IncidentRecord[]): TimelineEvent[] {
  return buildTimelineEvents(data, incidents.filter((incident) =>
    incident.domain.toLowerCase() === "wifi"), []).filter((event) => event.kind === "incident");
}

export function escapeHover(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}
