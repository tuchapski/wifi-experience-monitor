const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/profileValidation.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
const validate = loaded.exports.validateProfileConfiguration;

function configuration() {
  return {
    schema_version: 1,
    sampling: { wifi_interval_seconds: 5 },
    tests: {
      gateway: { enabled: true, interval_seconds: 5, timeout_seconds: 6,
        automatic_gateway: true, target: null },
      dns: { enabled: true, interval_seconds: 10, timeout_seconds: null,
        query: "example.com" },
      internet: { enabled: true, interval_seconds: 30, timeout_seconds: 6,
        target: "1.1.1.1" },
      https: { enabled: true, interval_seconds: 60, timeout_seconds: 5,
        url: "https://example.com" },
    },
    thresholds: {
      wifi: { rssi_warning_dbm: -75, rssi_critical_dbm: -82,
        retry_warning_percent: 20, retry_critical_percent: 50,
        tx_failure_critical_percent: 5 },
      gateway: { latency_warning_ms: 50, packet_loss_warning_percent: 5,
        packet_loss_critical_percent: 20 },
      dns: { latency_warning_ms: 250 },
      internet: { latency_warning_ms: 150, packet_loss_warning_percent: 5,
        packet_loss_critical_percent: 20 },
      https: { response_warning_ms: 1000 },
    },
  };
}

test("accepts a valid multi-cadence profile", () => {
  assert.deepEqual(validate(configuration()), []);
});

test("rejects a test interval that is not a sampling multiple", () => {
  const value = configuration();
  value.tests.dns.interval_seconds = 7;
  assert.match(validate(value).join(" "), /dns interval.*integer multiple/i);
});

test("validates explicit gateway and severity order", () => {
  const value = configuration();
  value.tests.gateway.automatic_gateway = false;
  value.thresholds.wifi.rssi_critical_dbm = -70;
  const errors = validate(value).join(" ");
  assert.match(errors, /Gateway target is required/);
  assert.match(errors, /Critical RSSI must be lower/);
});

test("accepts legacy thresholds without adaptive baseline", () => {
  assert.deepEqual(validate(configuration()), []);
});

test("validates adaptive baseline sample and sigma ordering", () => {
  const value = configuration();
  value.thresholds.adaptive_baseline = {
    enabled: true,
    lookback_hours: 24,
    minimum_samples: 100,
    max_samples: 50,
    warning_sigma: 6,
    critical_sigma: 5,
  };
  const errors = validate(value).join(" ");
  assert.match(errors, /maximum samples/i);
  assert.match(errors, /critical deviation/i);
});
