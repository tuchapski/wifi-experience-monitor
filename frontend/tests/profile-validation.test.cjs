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
    application_targets: [],
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

test("accepts legacy thresholds without service SLO", () => {
  assert.deepEqual(validate(configuration()), []);
});

test("validates service SLO window and target ordering", () => {
  const value = configuration();
  value.thresholds.service_slo = {
    enabled: true,
    window_size: 10,
    minimum_samples: 20,
    gateway: {
      availability_warning_percent: 95,
      availability_critical_percent: 99,
      latency_p95_warning_ms: 100,
      latency_p95_critical_ms: 50,
      packet_loss_p95_warning_percent: 20,
      packet_loss_p95_critical_percent: 5,
    },
    internet: {
      availability_warning_percent: 99,
      availability_critical_percent: 95,
      latency_p95_warning_ms: 150,
      latency_p95_critical_ms: 300,
      packet_loss_p95_warning_percent: 5,
      packet_loss_p95_critical_percent: 20,
    },
    dns: {
      availability_warning_percent: 99,
      availability_critical_percent: 95,
      latency_p95_warning_ms: 250,
      latency_p95_critical_ms: 500,
      packet_loss_p95_warning_percent: null,
      packet_loss_p95_critical_percent: null,
    },
    https: {
      availability_warning_percent: 99,
      availability_critical_percent: 95,
      latency_p95_warning_ms: 1000,
      latency_p95_critical_ms: 2000,
      packet_loss_p95_warning_percent: null,
      packet_loss_p95_critical_percent: null,
    },
  };
  const errors = validate(value).join(" ");
  assert.match(errors, /minimum samples/i);
  assert.match(errors, /Gateway service-SLO availability/i);
  assert.match(errors, /Gateway service-SLO latency/i);
  assert.match(errors, /Gateway service-SLO packet-loss/i);
});

test("validates connection-cycle stage milestone threshold ordering", () => {
  const value = configuration();
  value.thresholds.connection_cycle = {
    window_size: 20,
    minimum_samples: 5,
    p95_warning_ms: 8000,
    p95_critical_ms: 15000,
    stages: {
      association: { p95_warning_ms: 1500, p95_critical_ms: 1000 },
      authentication: { p95_warning_ms: 3000, p95_critical_ms: 6000 },
      ipv4: { p95_warning_ms: 5000, p95_critical_ms: 10000 },
      gateway: { p95_warning_ms: 6000, p95_critical_ms: 12000 },
      dns: { p95_warning_ms: 7000, p95_critical_ms: 14000 },
    },
  };
  const errors = validate(value).join(" ");
  assert.match(errors, /association connection-cycle stage P95 critical/i);
});

test("validates application target names, cadence and target shape", () => {
  const value = configuration();
  value.application_targets = [
    { name: "Portal", kind: "http", target: "not-a-url", port: null,
      enabled: true, interval_seconds: 7, timeout_seconds: 5 },
    { name: "portal", kind: "tcp", target: "tcp://db.example.com", port: null,
      enabled: true, interval_seconds: 10, timeout_seconds: 5 },
  ];
  const errors = validate(value).join(" ");
  assert.match(errors, /must be unique/i);
  assert.match(errors, /Portal interval.*integer multiple/i);
  assert.match(errors, /absolute HTTP\/HTTPS URL/i);
  assert.match(errors, /TCP port/i);
  assert.match(errors, /TCP target.*host name or IP/i);
});

test("accepts valid HTTP, TCP and DNS application targets", () => {
  const value = configuration();
  value.application_targets = [
    { name: "Portal", kind: "http", target: "https://portal.example.com/health", port: null,
      enabled: true, interval_seconds: 10, timeout_seconds: 5 },
    { name: "Database", kind: "tcp", target: "db.example.com", port: 5432,
      enabled: true, interval_seconds: 30, timeout_seconds: 3 },
    { name: "Identity DNS", kind: "dns", target: "login.example.com", port: null,
      enabled: true, interval_seconds: 60, timeout_seconds: 2 },
  ];
  assert.deepEqual(validate(value), []);
});
