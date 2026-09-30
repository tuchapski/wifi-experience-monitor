const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/rfEnvironment.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);

const { rfBandLabel, summarizeRfEnvironment } = loaded.exports;

const scan = {
  scan_id: "rfs_test",
  sequence: 1,
  observed_at: "2026-09-29T20:00:00Z",
  received_at: "2026-09-29T20:00:01Z",
  interface: "wlp0s20f3",
  duration_ms: 100,
  bsses: [
    {
      bssid: "98:7e:ca:8a:3e:0e", ssid: "AeP", frequency_mhz: 5805,
      channel: 161, band: "5ghz", rssi_dbm: -61, associated: true,
    },
    {
      bssid: "86:7e:ca:8a:3e:0e", ssid: "AeP", frequency_mhz: 5805,
      channel: 161, band: "5ghz", rssi_dbm: -68, associated: false,
    },
    {
      bssid: "98:7e:ca:8a:3e:0f", ssid: "AeP", frequency_mhz: 2437,
      channel: 6, band: "2.4ghz", rssi_dbm: -64, associated: false,
    },
    {
      bssid: "84:01:12:5e:d1:da", ssid: "Claro", frequency_mhz: 2412,
      channel: 1, band: "2.4ghz", rssi_dbm: -68, associated: false,
    },
    {
      bssid: "50:e0:39:07:e0:e1", ssid: "Desktop_F7824671", frequency_mhz: 2422,
      channel: 3, band: "2.4ghz", rssi_dbm: -76, associated: false,
    },
    {
      bssid: "e8:45:8b:5e:45:88", ssid: "VIVOFIBRA-WIFI6-4588", frequency_mhz: 2437,
      channel: 6, band: "2.4ghz", rssi_dbm: -86, associated: false,
    },
    {
      bssid: "4c:c5:3e:ff:75:a1", ssid: "Desktop_F5646388", frequency_mhz: 2442,
      channel: 7, band: "2.4ghz", rssi_dbm: -76, associated: false,
    },
  ],
};

test("summarizes the AX201 BSS neighborhood without inventing utilization", () => {
  const summary = summarizeRfEnvironment(scan, {
    ssid: "AeP",
    bssid: "98:7e:ca:8a:3e:0e",
    channel: 161,
  });

  assert.equal(summary.visibleBss, 7);
  assert.equal(summary.visibleSsids, 5);
  assert.equal(summary.sameSsid, 3);
  assert.equal(summary.sameChannel, 2);
  assert.equal(summary.strongNeighbors, 3);
  assert.equal(summary.associated.bssid, "98:7e:ca:8a:3e:0e");
});

test("selects the strongest same-SSID alternative and calculates RSSI delta", () => {
  const summary = summarizeRfEnvironment(scan, {
    ssid: "AeP",
    bssid: "98:7e:ca:8a:3e:0e",
    channel: 161,
  });

  assert.equal(summary.bestSameSsidAlternative.bssid, "98:7e:ca:8a:3e:0f");
  assert.equal(summary.bestSameSsidAlternative.rssi_dbm, -64);
  assert.equal(summary.alternativeDeltaDb, -3);
});

test("formats RF bands independently of negotiated client PHY", () => {
  assert.equal(rfBandLabel("2.4ghz"), "2.4 GHz");
  assert.equal(rfBandLabel("5ghz"), "5 GHz");
  assert.equal(rfBandLabel("6ghz"), "6 GHz");
  assert.equal(rfBandLabel("unknown"), "Unknown band");
});
