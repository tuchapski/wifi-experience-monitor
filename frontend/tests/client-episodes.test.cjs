const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");
function load(file) {
  const compiled = ts.transpileModule(readFileSync(resolve(__dirname, `../src/${file}.ts`), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(require, loaded, loaded.exports);
  return loaded.exports;
}
const { episodeStatus } = load("clientEpisodePresentation");
const { clientEpisodeHash, parseWorkspaceRoute } = load("diagnosticRoutes");
test("episode bookmarks keep individual client and episode identifiers", () => {
  assert.deepEqual(parseWorkspaceRoute(clientEpisodeHash("agent/a", "episode/b")), {
    section: "agents", agentId: "agent/a", recordingId: null, episodeId: "episode/b",
  });
});
test("a displayed open episode expires to unknown without implying recovery", () => {
  const now = Date.parse("2026-10-02T18:00:00Z");
  const episode = { status: "active", closed_at: null, last_observed_at: new Date(now).toISOString() };
  assert.equal(episodeStatus(episode, now + 30000), "active");
  assert.equal(episodeStatus(episode, now + 31000), "unknown");
  assert.equal(episodeStatus({ ...episode, status: "recovered", closed_at: episode.last_observed_at }, now + 60000), "recovered");
  assert.equal(episode.status, "active");
});
