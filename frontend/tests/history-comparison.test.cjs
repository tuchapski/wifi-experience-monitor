const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/historyComparisonModel.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
const { compareHistoryWindows } = loaded.exports;

test("manual comparison uses the chosen reference period and retains missing metrics", () => {
  const current = {
    interface: "wlan0", start: "2026-09-23T10:00:00Z", end: "2026-09-23T11:00:00Z",
    summary: { sample_count: 50, metrics: { signal_dbm: { avg: -55 },
      internet_latency_avg_ms: { avg: null } } },
  };
  const reference = {
    interface: "wlan0", start: "2026-09-21T08:00:00Z", end: "2026-09-21T10:00:00Z",
    summary: { sample_count: 20, metrics: { signal_dbm: { avg: -65 },
      internet_latency_avg_ms: { avg: 40 } } },
  };
  const result = compareHistoryWindows(current, reference);
  assert.equal(result.previous_start, reference.start);
  assert.equal(result.previous_end, reference.end);
  assert.equal(result.current.sample_count, 50);
  assert.equal(result.previous.sample_count, 20);
  assert.equal(result.current.metrics.internet_latency_avg_ms.avg, null);
  assert.equal(compareHistoryWindows(current, { ...reference, interface: "wlan1" }), null);
});
