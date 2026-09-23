const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/dashboardState.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);

const {
  applicationsDashboardState,
  outcomeDashboardState,
  overallDashboardState,
  wifiDashboardState,
} = loaded.exports;


test("maps definitive probe outcomes without treating collection errors as failures", () => {
  assert.equal(outcomeDashboardState({ status: "passed" }), "healthy");
  assert.equal(outcomeDashboardState({ status: "failed" }), "critical");
  assert.equal(outcomeDashboardState({ status: "error" }), "unavailable");
  assert.equal(outcomeDashboardState({ status: "skipped" }), "unavailable");
});


test("application summary distinguishes failure from partial evidence", () => {
  assert.equal(applicationsDashboardState({
    Portal: { status: "passed" },
    ERP: { status: "failed" },
  }), "critical");

  assert.equal(applicationsDashboardState({
    Portal: { status: "passed" },
    ERP: { status: "error" },
  }), "warning");

  assert.equal(applicationsDashboardState({
    Portal: { status: "error" },
  }), "unavailable");
});


test("wifi state requires association and complete evidence before healthy", () => {
  const base = {
    wifi: { associated: true },
    diagnostic: { complete: true, findings: [] },
  };
  assert.equal(wifiDashboardState(base), "healthy");
  assert.equal(wifiDashboardState({
    ...base,
    diagnostic: {
      complete: true,
      findings: [{ domain: "wifi", severity: "warning" }],
    },
  }), "warning");
  assert.equal(wifiDashboardState({
    ...base,
    wifi: { associated: false },
  }), "critical");
});


test("overall dashboard does not label incomplete or errored evidence healthy", () => {
  const complete = {
    diagnostic: { overall_status: "healthy", complete: true },
    collector_errors: [],
  };
  assert.equal(overallDashboardState(complete), "healthy");
  assert.equal(overallDashboardState({
    ...complete,
    diagnostic: { overall_status: "healthy", complete: false },
  }), "unavailable");
  assert.equal(overallDashboardState({
    ...complete,
    collector_errors: ["collector failed"],
  }), "unavailable");
});
