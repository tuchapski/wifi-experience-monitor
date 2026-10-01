const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/RecordingRfSummary.tsx"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
const Summary = loaded.exports.default;

function fixture() {
  const empty = { sample_count: 0, minimum: null, average: null, maximum: null };
  return {
    scan_count: 2501,
    total_bss_observations: 9000,
    unique_bss: 42,
    unique_ssids: 5,
    first_scan_at: "2026-09-29T20:00:00Z",
    last_scan_at: "2026-09-29T22:00:00Z",
    visible_neighbors: { sample_count: 2501, minimum: 0, average: 1.5, maximum: 40 },
    same_channel_neighbors: empty,
    same_ssid_neighbors: empty,
    strong_neighbors: empty,
    strong_neighbor_threshold_dbm: -70,
    best_same_ssid_delta_db: empty,
    stronger_same_ssid_scan_count: 0,
    stronger_same_ssid_percent: null,
    association_transition_pairs: 0,
    associated_bssid_changes: 0,
    associated_frequency_changes: 0,
    neighborhood_changed_pairs: 0,
    neighborhood_transition_pairs: 2500,
    visible_bss_additions: 0,
    visible_bss_removals: 0,
    scans_with_association: 0,
    association_coverage_percent: 0,
    maximum_scan_gap_seconds: 60,
  };
}

test("summary shows full stored evidence, denominators and unavailable comparisons", () => {
  const html = renderToStaticMarkup(React.createElement(Summary, { summary: fixture() }));
  assert.match(html, /All 2,501 stored RF scans/);
  assert.match(html, /2501\/2501 valid scans/);
  assert.match(html, /0\/2501 valid scans/);
  assert.match(html, /<strong>—<\/strong>/);
  assert.match(html, /0 % association visible/);
  assert.match(html, /not time-weighted exposure/);
  assert.doesNotMatch(html, /NaN|undefined|Infinity/);
});

test("stronger alternative percent uses comparable scans rather than all scans", () => {
  const summary = fixture();
  summary.best_same_ssid_delta_db = { sample_count: 10, minimum: -5, average: 2, maximum: 8 };
  summary.stronger_same_ssid_scan_count = 4;
  summary.stronger_same_ssid_percent = 40;
  const html = renderToStaticMarkup(React.createElement(Summary, { summary }));
  assert.match(html, /40 %/);
  assert.match(html, /4\/10 comparable scans/);
  assert.match(html, /roaming suitability is not evaluated/);
});
