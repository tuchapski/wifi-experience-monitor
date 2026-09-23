const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/historyEventsModel.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);

const { buildTimelineEvents, buildWifiIncidentEvents, escapeHover } = loaded.exports;
const start = "2026-09-22T10:00:00Z";
const end = "2026-09-22T11:00:00Z";

function windowFixture() {
  return {
    interface: "wlan0", start, end,
    events: [
      { code: "BSSID_CHANGE", field: "bssid", message: "AP changed", timestamp: "2026-09-22T10:30:00Z" },
      { code: "SSID_CHANGE", field: "ssid", message: "Outside", timestamp: "2026-09-22T12:00:00Z" },
      { code: "CHANNEL_CHANGE", field: "channel", message: "Channel 44", timestamp: "2026-09-22T10:31:00Z" },
    ],
    connection_cycles: [{
      session_id: "session-1", started_at: "2026-09-22T10:28:00Z",
      completed_at: null, last_observed_at: "2026-09-22T10:29:00Z",
      session_type: "roam", state: "connecting", ssid: "Office", bssid: "AA:BB", total_time_ms: null,
    }],
    application_availability: { targets: [{
      identity: "http:internal", name: "Internal", kind: "http",
      outages: [{ started_at: "2026-09-22T10:40:00Z", ended_at: null, failure_count: 2, recovered: false }],
    }] },
  };
}

test("event intervals share the history window without inventing recovery or start times", () => {
  const incidents = [
    { id: 1, code: "DNS_FAILURE", severity: "critical", message: "DNS down",
      started_at: "2026-09-22T09:45:00Z", ended_at: "2026-09-22T10:05:00Z" },
    { id: 2, code: "OLD", severity: "warning", message: "Outside",
      started_at: "2026-09-22T08:00:00Z", ended_at: "2026-09-22T08:10:00Z" },
  ];
  const episodes = [{ episode_id: "e1", severity: "warning", incident_count: 1,
    primary_domain: "dns", correlation_status: "correlated",
    started_at: "2026-09-22T10:50:00Z", ended_at: null }];

  const events = buildTimelineEvents(windowFixture(), incidents, episodes);
  assert.deepEqual(events.map((event) => event.kind), [
    "incident", "connection", "roam", "environment", "outage", "episode",
  ]);
  assert.equal(events[0].start, "2026-09-22T10:00:00.000Z");
  assert.equal(events[0].recordedStart, "2026-09-22T09:45:00Z");
  assert.equal(events[0].end, "2026-09-22T10:05:00.000Z");
  assert.equal(events.find((event) => event.kind === "connection").end, "2026-09-22T10:29:00.000Z");
  assert.equal(events.find((event) => event.kind === "outage").end, "2026-09-22T11:00:00.000Z");
  assert.equal(events.find((event) => event.kind === "episode").scope, "sensor");
  assert.equal(events.find((event) => event.kind === "roam").end, null);
});

test("invalid and outside timestamps are omitted; hover content is escaped", () => {
  const events = buildTimelineEvents({ ...windowFixture(), start: end, end: start }, [], []);
  assert.deepEqual(events, []);
  assert.equal(escapeHover('<img src="x" onerror=\'alert(1)\'>&'),
    "&lt;img src=&quot;x&quot; onerror=&#39;alert(1)&#39;&gt;&amp;");
});

test("Wi-Fi incident overlay excludes other domains and keeps observed interval bounds", () => {
  const incidents = [
    { id: 1, domain: "wifi", code: "WIFI_LOW_SIGNAL", severity: "warning", message: "Weak signal",
      started_at: "2026-09-22T09:55:00Z", ended_at: "2026-09-22T10:15:00Z" },
    { id: 2, domain: "dns", code: "DNS_FAILURE", severity: "critical", message: "DNS down",
      started_at: "2026-09-22T10:20:00Z", ended_at: null },
  ];
  const events = buildWifiIncidentEvents(windowFixture(), incidents);
  assert.deepEqual(events.map((event) => event.label), ["WIFI_LOW_SIGNAL · warning"]);
  assert.equal(events[0].start, "2026-09-22T10:00:00.000Z");
  assert.equal(events[0].end, "2026-09-22T10:15:00.000Z");
  assert.equal(events[0].scope, "sensor");
});
