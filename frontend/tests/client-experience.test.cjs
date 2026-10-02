const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const ts = require("typescript");

const compiled = ts.transpileModule(readFileSync(resolve(__dirname, "../src/ClientExperienceContent.tsx"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
const Content = loaded.exports.default;
const time = "2026-10-02T17:00:00Z";

function fixture(status = "observed_ok") {
  return { agent_id: "agt_test", evaluated_at: time, state_observed_at: time,
    state_received_at: time, agent_online: true, max_measurement_age_seconds: 30,
    current_outcomes: 5, total_outcomes: 5, outcome_coverage_percent: 100,
    collector_errors: [], limitations: [],
    domains: ["wifi_rf", "local_network", "dns", "internet", "application"].map(domain => ({
      domain, label: domain === "application" ? "Application" : domain, status,
      explanation: "Direct evidence", target: "example.com",
      measurements: [{ metric: domain + ".outcome", label: "Outcome", value: true, unit: null,
        quality: "current", age_seconds: 0, observed_at: time, source: "synthetic",
        sample_count: 1, interval_seconds: null },
        { metric: domain + ".latency_ms", label: "Latency", value: 0, unit: "ms",
          quality: "current", age_seconds: 0, observed_at: time, source: "synthetic",
          sample_count: 1, interval_seconds: null }],
    })),
  };
}

function render(data, elapsedSeconds = 0) {
  return renderToStaticMarkup(React.createElement(Content, { data, elapsedSeconds }));
}

test("shows current outcome coverage, zero latency and expandable evidence", () => {
  const html = render(fixture());
  assert.match(html, /5\/5 current outcomes/);
  assert.match(html, /0 ms/);
  assert.match(html, /<summary>View evidence<\/summary>/);
  assert.match(html, /Tests responding/);
  assert.match(html, /does not assign a root cause/);
});

test("application failure stays visible even when other domains succeed", () => {
  const data = fixture();
  data.domains[4].status = "failure";
  data.domains[4].measurements[0].value = false;
  const html = render(data);
  assert.match(html, /role="status">Failure observed/);
  assert.match(html, /<h3>Application<\/h3><span>Failure observed/);
});

test("legacy timing and invalid data cannot look like current success", () => {
  const data = fixture("partial");
  for (const domain of data.domains) {
    for (const item of domain.measurements) { item.quality = "legacy"; item.observed_at = null; item.age_seconds = null; }
  }
  data.domains[0].measurements[1].value = NaN;
  const html = render(data);
  assert.match(html, /0\/5 current outcomes/);
  assert.match(html, /Observation time not reported/);
  assert.doesNotMatch(html, /NaN|Infinity|role="status">Tests responding/);
});

test("cached UI expires each probe and the snapshot when updates stop", () => {
  const data = fixture();
  data.domains[4].measurements[0].age_seconds = 29;
  assert.match(render(data, 2), /4\/5 current outcomes/);
  assert.match(render(data, 31), /role="status">Stale evidence/);
  data.state_observed_at = "2026-10-02T16:59:31Z";
  assert.match(render(data, 2), /0\/5 current outcomes/);
});

test("unavailable timing and errors are escaped, not presented as service failure", () => {
  const data = fixture();
  data.domains[2].status = "collection_error";
  data.domains[2].explanation = "<script>error</script>";
  data.domains[2].target = "<b>unsafe</b>";
  const html = render(data);
  assert.match(html, /Collection error/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>|role="status">Failure observed/);
});
