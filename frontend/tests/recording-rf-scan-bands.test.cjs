const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const ts = require("typescript");

function load(name) {
  const compiled = ts.transpileModule(readFileSync(resolve(__dirname, `../src/${name}`), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
  return loaded.exports;
}
const { buildRfScanBands } = load("recordingRfScanBands.ts");
const Bands = load("RecordingRfScanBands.tsx").default;
const Context = load("RecordingRfScanContext.tsx").default;
const base = Date.parse("2026-10-01T12:00:00Z");
const bounds = { start: base, end: base + 10000 };
function window(id, start, end) {
  return {
    scan_id: id, interface: "wlan0",
    started_at: new Date(base + start).toISOString(),
    ended_at: new Date(base + end).toISOString(), duration_ms: end - start,
  };
}

test("scan bands clip at recording bounds, sort and deduplicate without extending time", () => {
  const bands = buildRfScanBands([
    window("right", 9000, 11000), window("left", -1000, 1000),
    window("right", 9000, 11000), window("outside", 12000, 13000),
    window("reversed", 5000, 4000), { ...window("invalid", 1, 2), ended_at: "invalid" },
  ], bounds);
  assert.deepEqual(bands.map(({ scan, startFraction, endFraction }) =>
    [scan.scan_id, startFraction, endFraction]), [["left", 0, 0.1], ["right", 0.9, 1]]);
  assert.equal(bands[0].scan.duration_ms, 2000);
});

test("missing or invalid timeline returns no bands", () => {
  for (const limits of [null, { start: NaN, end: base }, { start: base, end: base },
    { start: base + 1, end: base }, { start: base, end: Infinity }]) {
    assert.deepEqual(buildRfScanBands([window("valid", 1, 2)], limits), []);
  }
});

test("minimum visible width stays inside chart and keeps original interval in tooltip", () => {
  const bands = buildRfScanBands([window("edge", 10000, 10000)], bounds);
  const html = renderToStaticMarkup(React.createElement("svg", {}, React.createElement(Bands, {
    bands, left: 16, width: 688, top: 28, height: 126,
  })));
  assert.match(html, /x="703.2"/);
  assert.match(html, /width="0.8"/);
  assert.match(html, /2026-10-01T12:00:10.000Z/);
  assert.match(html, /0.0 ms/);
  assert.match(html, /<title>Estimated RF scan/);
});

test("context distinguishes partial coverage, invalid timings and empty evidence", () => {
  const render = (data, error = null) => renderToStaticMarkup(React.createElement(Context, {
    data, error, enabled: true, onToggle() {},
  }));
  const partial = render({ total_scans: 2500, loaded_scans: 2000, invalid_windows: 1,
    truncated: true, windows: [window("valid", 1, 2)] });
  assert.match(partial, /Partial coverage: only the latest 2,000/);
  assert.match(partial, /Earlier periods have no scan overlay/);
  assert.match(partial, /invalid timing and are omitted/);
  assert.match(partial, /Temporal context, not causal diagnosis/);
  assert.match(partial, /checked=""/);
  const empty = render({ total_scans: 0, loaded_scans: 0, invalid_windows: 0,
    truncated: false, windows: [] });
  assert.match(empty, /No successful RF scans are stored/);
  assert.doesNotMatch(empty, /Partial coverage/);
  assert.match(render(null), /Loading RF scan windows/);
  assert.match(render(null, "offline"), /unavailable: offline/);
});
