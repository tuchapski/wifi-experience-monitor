const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");

const source = readFileSync(resolve(__dirname, "../src/diagnosticRoutes.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
const { parseWorkspaceRoute, diagnosticsAgentHash, diagnosticsRecordingHash } = loaded.exports;

test("existing recording bookmarks open Diagnostics with the same Agent and recording", () => {
  const legacy = parseWorkspaceRoute("#agents/agt_01/recordings/rec_02");
  const current = parseWorkspaceRoute(diagnosticsRecordingHash("agt_01", "rec_02"));
  assert.deepEqual(legacy, current);
  assert.deepEqual(current, { section: "diagnostics", agentId: "agt_01", recordingId: "rec_02" });
});

test("Agent selection and recording links preserve encoded identifiers", () => {
  assert.deepEqual(parseWorkspaceRoute(diagnosticsAgentHash("agent/a")), {
    section: "diagnostics", agentId: "agent/a", recordingId: null,
  });
  assert.deepEqual(parseWorkspaceRoute(diagnosticsRecordingHash("agent/a", "record/b")), {
    section: "diagnostics", agentId: "agent/a", recordingId: "record/b",
  });
  assert.deepEqual(parseWorkspaceRoute("#agents/agt_01"), {
    section: "agents", agentId: "agt_01", recordingId: null,
  });
});
