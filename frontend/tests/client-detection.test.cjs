const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const ts = require("typescript");
const compiled = ts.transpileModule(readFileSync(resolve(__dirname, "../src/ClientDetectionContent.tsx"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
const Content = loaded.exports.default;
const time = "2026-10-02T18:00:00Z";
function fixture() {
  return { agent_id: "agt_test", evaluated_at: time, enabled: true, status: "active", active_count: 1,
    profile_version: "exp_test", applied_version: "exp_test", detector_version: "client-detector-v1",
    limitations: ["An evidence gap does not confirm recovery."], findings: [{ rule_id: "network.gateway_latency_ms",
      domain: "local_network", metric: "network.gateway_latency_ms", label: "Latency", status: "active", kind: "objective",
      previous_status: "candidate", reason: "Configured performance objective exceeded.", target: "192.0.2.1", value: 100,
      unit: "ms", objective: 50, observed_at: time, since: time, observed_duration_seconds: 15,
      consecutive_samples: 4, evidence_gap: false, context: { ssid: "Office", interface: "wlan0", band: "5ghz" },
      baseline: { status: "forming", samples: 10, median: null, mad: null, p95: null, upper_limit: null, established_at: null } }],
  };
}
function render(data, elapsedSeconds = 0) { return renderToStaticMarkup(React.createElement(Content, { data, elapsedSeconds })); }
test("shows observed degradation with objective, duration, target and reference formation", () => {
  const html = render(fixture());
  assert.match(html, /Active degradation/);
  assert.match(html, /Objective ≤ 50 ms/);
  assert.match(html, /15s · 4 consecutive measurement/);
  assert.match(html, /Forming · 10 successful samples/);
  assert.match(html, /192.0.2.1/);
});
test("cached findings expire without implying recovery", () => {
  const html = render(fixture(), 31);
  assert.match(html, /Evidence incomplete/);
  assert.match(html, /0 confirmed rule/);
  assert.match(html, /active · recovery remains unconfirmed/);
  assert.doesNotMatch(html, />Active degradation</);
});
test("disabled and pending profile states stay explicit", () => {
  const data = { ...fixture(), enabled: false, status: "disabled", findings: [] };
  assert.match(render(data), /Detection disabled/);
  assert.match(render({ ...data, enabled: true, status: "pending_profile" }), /Waiting for Agent to apply profile/);
});
test("frozen reference reports expected range and escaped contextual text", () => {
  const data = fixture();
  data.findings[0].kind = "relative";
  data.findings[0].target = '<script>alert("x")</script>';
  data.findings[0].baseline = { status: "ready", samples: 30, median: 5, mad: 0, p95: 5, upper_limit: 15, established_at: time };
  const html = render(data);
  assert.match(html, /Frozen · 30 samples/);
  assert.match(html, /Median 5 ms · p95 5 ms · upper limit 15 ms/);
  assert.match(html, /Change against contextual reference/);
  assert.doesNotMatch(html, /<script>/);
});
