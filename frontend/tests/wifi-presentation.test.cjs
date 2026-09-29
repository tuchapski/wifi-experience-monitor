const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/wifiPresentation.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);

const { describeWifiConnection, wifiBandLabel } = loaded.exports;

test("maps frequencies to the client-visible Wi-Fi band", () => {
  assert.equal(wifiBandLabel(2412), "2.4 GHz");
  assert.equal(wifiBandLabel(5805), "5 GHz");
  assert.equal(wifiBandLabel(5975), "6 GHz");
  assert.equal(wifiBandLabel(null), "—");
});

test("maps negotiated PHY names to Wi-Fi generation and IEEE family", () => {
  assert.deepEqual(
    describeWifiConnection({ frequency_mhz: 2412, tx_phy: "HT", rx_phy: "HT" }),
    {
      band: "2.4 GHz",
      frequency: "2412 MHz",
      generation: "Wi-Fi 4",
      ieee: "802.11n",
      shorthand: "n",
      phy: "HT",
    },
  );

  assert.equal(
    describeWifiConnection({ frequency_mhz: 5180, tx_phy: "VHT" }).generation,
    "Wi-Fi 5",
  );
  assert.equal(
    describeWifiConnection({ frequency_mhz: 5805, tx_phy: "HE" }).generation,
    "Wi-Fi 6",
  );
  assert.equal(
    describeWifiConnection({ frequency_mhz: 5975, tx_phy: "HE" }).generation,
    "Wi-Fi 6E",
  );
  assert.equal(
    describeWifiConnection({ frequency_mhz: 5975, tx_phy: "EHT" }).generation,
    "Wi-Fi 7",
  );
});

test("does not invent a Wi-Fi generation when the driver does not report PHY", () => {
  const presentation = describeWifiConnection({
    connected: true,
    frequency_mhz: 5805,
    tx_rate_mbps: 600,
  });
  assert.equal(presentation.band, "5 GHz");
  assert.equal(presentation.generation, "Unavailable");
  assert.equal(presentation.ieee, "PHY not reported");
});
