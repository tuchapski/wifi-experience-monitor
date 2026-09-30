const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/recordingRfTimeline.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);

const { buildRecordingRfTimeline } = loaded.exports;

function bss(bssid, ssid, rssi, associated = false, channel = 161, band = "5ghz") {
  return {
    bssid,
    ssid,
    frequency_mhz: band === "5ghz" ? 5805 : 2437,
    channel,
    band,
    rssi_dbm: rssi,
    associated,
    channel_width_mhz: 80,
    beacon_interval_tu: 100,
    capability: null,
    privacy: true,
    security: ["RSN"],
    phy_capabilities: ["HE"],
    bss_load_station_count: null,
    bss_load_channel_utilization_raw: null,
    last_seen_ms: 10,
  };
}

function scan(id, observedAt, bsses) {
  return {
    scan_id: id,
    sequence: Number(id.replace(/\D/g, "")) || 1,
    observed_at: observedAt,
    interface: "wlp0s20f3",
    duration_ms: 120,
    received_at: observedAt,
    bsses,
  };
}

test("summarizes RF evidence and associated BSSID changes", () => {
  const data = buildRecordingRfTimeline([
    scan("rfs_3", "2026-09-29T20:02:00Z", [
      bss("98:7e:ca:8a:3e:0f", "AeP", -58, true, 6, "2.4ghz"),
      bss("98:7e:ca:8a:3e:0e", "AeP", -66),
    ]),
    scan("rfs_1", "2026-09-29T20:00:00Z", [
      bss("98:7e:ca:8a:3e:0e", "AeP", -60, true),
      bss("86:7e:ca:8a:3e:0e", "AeP", -68),
      bss("84:01:12:5e:d1:da", "Claro", -65, false, 1, "2.4ghz"),
    ]),
    scan("rfs_2", "2026-09-29T20:01:00Z", [
      bss("98:7e:ca:8a:3e:0e", "AeP", -62, true),
      bss("98:7e:ca:8a:3e:0f", "AeP", -64, false, 6, "2.4ghz"),
    ]),
  ]);

  assert.equal(data.summary.scanCount, 3);
  assert.equal(data.summary.totalBssObservations, 7);
  assert.equal(data.summary.uniqueBss, 4);
  assert.equal(data.summary.uniqueSsids, 2);
  assert.equal(data.summary.associatedBssidChanges, 1);
  assert.equal(data.summary.associationCoveragePercent, 100);
  assert.equal(data.views[2].associatedChanged, true);
  assert.equal(data.views[0].bestSameSsidAlternative.bssid, "86:7e:ca:8a:3e:0e");
  assert.equal(data.views[0].alternativeDeltaDb, -8);
});

test("keeps missing association explicit instead of inventing a BSSID", () => {
  const data = buildRecordingRfTimeline([
    scan("rfs_1", "2026-09-29T20:00:00Z", [
      bss("98:7e:ca:8a:3e:0e", "AeP", -60, false),
    ]),
  ]);

  assert.equal(data.summary.associationCoveragePercent, 0);
  assert.equal(data.summary.associatedBssidChanges, 0);
  assert.equal(data.views[0].associated, null);
  assert.equal(data.views[0].sameSsid, 0);
});
