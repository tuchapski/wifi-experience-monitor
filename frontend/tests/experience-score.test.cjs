// Dependency-free rendering regression tests using the existing TS/React tools.
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const source = readFileSync(resolve(__dirname, "../src/ExperienceScorePanel.tsx"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
const Panel = loaded.exports.default;
const render = score => renderToStaticMarkup(React.createElement(Panel, { score }));

function fixture(overrides = {}) {
  return {
    policy_version: "experience-v1", value: 100, status: "complete",
    coverage_percent: 100, minimum_coverage_percent: 70, reasons: ["Example policy"],
    components: [{
      key: "dns", label: "DNS", weight: 15, coverage_percent: 100, score: 100,
      scope: "host", available_weight: 15, effective_weight: 15,
      contribution: 15, deduction: 0,
      metrics: [{
        key: "latency", label: "DNS resolution time", weight: 100, unit: "ms",
        value: 10, score: 100, state: "measured", reason: "Observed 10 ms",
        rule: "Linear interpolation: test anchors",
      }],
    }],
    ...overrides,
  };
}

test("old snapshots render without inventing a score", () => {
  for (const score of [undefined, null]) {
    assert.match(render(score), /This sample has no score/);
    assert.doesNotMatch(render(score), /NaN|undefined|score-value/);
  }
});

test("complete score includes coverage, weights, contribution and evidence", () => {
  const html = render(fixture());
  for (const text of ["Complete assessment", "experience-v1", "Evidence coverage",
    "Base weight", "Effective weight", "Points deducted", "Observed 10 ms",
    "Host route", "not a statistical confidence"]) {
    assert.ok(html.includes(text), text);
  }
});

test("zero is shown as a score, not unavailable", () => {
  assert.match(render(fixture({value: 0})), /class="score-value">0<small>/);
});

test("partial score explicitly stays provisional, including at 100", () => {
  const html = render(fixture({status: "partial", coverage_percent: 82}));
  assert.match(html, /Provisional/);
  assert.match(html, /value="82"/);
  assert.doesNotMatch(html, /Complete assessment/);
});

test("insufficient evidence has no numeric global score", () => {
  const html = render(fixture({value: null, status: "unavailable", coverage_percent: 30}));
  assert.match(html, /Insufficient evidence/);
  assert.match(html, /class="score-value">Unavailable/);
});

test("confirmed failures remain visible even with a high weighted average", () => {
  const score = fixture({value: 85});
  score.components[0].metrics[0].state = "failed";
  score.components[0].metrics[0].score = 0;
  assert.match(render(score), /Confirmed test\/association failure: DNS/);
});

test("non-finite numbers never leak into displayed scores", () => {
  assert.match(render(fixture({value: NaN})), /class="score-value">Unavailable/);
  assert.doesNotMatch(render(fixture({value: Infinity})), />Infinity/);
});

test("measurement explanations are escaped as text", () => {
  const html = render(fixture({reasons: ["<script>alert(1)</script>"]}));
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});
