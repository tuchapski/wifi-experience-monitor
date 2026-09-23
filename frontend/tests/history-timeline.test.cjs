const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/historyTimelineModel.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);

const {
  buildTimelineSeries,
  historicalOverview,
} = loaded.exports;


function windowFixture() {
  return {
    interface: "wlan0",
    start: "2026-09-22T10:00:00Z",
    end: "2026-09-22T11:00:00Z",
    bucket_seconds: 60,
    total_samples: 2,
    events: [{ code: "BSSID_CHANGE", field: "bssid", message: "AP changed", timestamp: "2026-09-22T10:30:00Z" }],
    points: [
      {
        timestamp: "2026-09-22T10:00:00Z",
        sample_count: 3,
        metrics: {
          signal_dbm: { avg: -60, min: -61, max: -59, count: 3, p50: -60, p95: -59, p99: -59 },
        },
      },
      {
        timestamp: "2026-09-22T10:01:00Z",
        sample_count: 3,
        metrics: {
          signal_dbm: { avg: null, min: null, max: null, count: 0, p50: null, p95: null, p99: null },
        },
      },
    ],
    connection_cycles: [{ session_id: "1" }, { session_id: "2" }],
    application_availability: {
      target_count: 1,
      targets: [{ outage_count: 2 }],
    },
  };
}


test("timeline preserves missing readings as gaps instead of zero", () => {
  const data = windowFixture();
  const series = buildTimelineSeries(data);
  const rssi = series.find((item) => item.key === "signal_dbm");

  assert.ok(rssi);
  assert.deepEqual(rssi.y, [-60, null]);
  assert.match(rssi.hoverText[0], /P95/);
  assert.match(rssi.hoverText[1], /Unavailable/);
});


test("timeline model keeps all eight historical metric series", () => {
  const series = buildTimelineSeries(windowFixture());
  assert.equal(series.length, 8);
  assert.deepEqual(
    [...new Set(series.map((item) => item.axis))],
    ["y", "y2", "y3", "y4"],
  );
});


test("historical overview counts events, cycles and observed application outages", () => {
  assert.deepEqual(historicalOverview(windowFixture()), {
    totalSamples: 2,
    bucketSeconds: 60,
    environmentEvents: 1,
    connectionCycles: 2,
    applicationOutages: 2,
  });
});
