# P0.3 — Continuous individual client detection

Base: `e4887d3` on `feature/v2-foundation`.

The client detail includes **Continuous detection** and an expandable editor for
targets and performance objectives. Detection starts disabled. Configure stable
targets relevant to the office, review the objectives, enable the profile and
save it. The existing Agent environment continues to control probes until a
profile is applied. The profile uses the current default gateway for LAN tests,
one system DNS query, one Internet ICMP target and one HTTPS application target.

## Runtime policy

- `GET/PUT /api/v1/agents/{id}/experience/profile` read/edit the policy.
- PUT requires `expected_version` (null on first creation), rejects stale edits
  with 409 and invalid values with 422. Identical saves retain the version and
  references; changed policies get a new version and explicit reference rebuild.
- Heartbeats carry the desired policy. The Agent waits for its old workers to
  finish, persists the new policy and rebuilds the synthetic runtime once. Old
  cached probes are discarded; new measurements identify the applied version.
- The last applied policy is saved in `data/agent/experience-profile.json`, bound
  to Agent identity and Server URL. A restart reuses it even while the Server is
  unavailable. A disabled policy restores the environment targets/cadence.
- Cadence is bounded to 5–20s and timeout to 1–10s, with at most one execution of
  each test in flight. These limits do not change RF scan policy. The metadata
  separates configured cadence from actual time between probe completions.
- Probes retain interface, target, starting SSID/band/BSSID and original clock.
  Results that started before a change of SSID/band cannot advance the new
  context's detector. DNS uses the system resolver and can be served from cache.

The desired and applied versions are visible under measurement limits; the
summary explicitly shows a pending policy. An applied Wi-Fi policy marker does
not imply all cached synthetic results already use it: each rule checks its own
measurement version and target.

## Incremental detector

`GET /api/v1/agents/{id}/experience/detection` is a read-only evaluation. New
Current State publications advance the detector in the same database transaction
as the snapshot. Publishing and profile changes lock the same Agent row.
Repeated/older measurements do not advance counters, references or recovery.
GET and browser polling do not create detections.

- Explicit boolean disconnection or failed probe is an immediate availability
  finding. It remains independent of other successful tests.
- Latency/HTTP total time, ICMP loss, optional jitter and TTFB have configurable
  point objectives. These are per-probe objectives, not rolling availability or
  percentile SLO compliance. Four-packet ICMP loss has 25 percentage-point steps.
- Performance findings require at least three distinct observations and 15s of
  comparable evidence by default. Confirmation uses both count and elapsed
  observation time, so the actual cadence controls detection delay.
- Recovery requires at least two new successful observations spanning 10s by
  default. Numeric recovery uses 80% of the objective/relative deviation range,
  reducing threshold chatter. Missing evidence never confirms recovery.
- Stale, invalid, legacy, mismatched-profile/context and collection-error results
  are unknown. Gaps longer than 30s reset confirmation/recovery streaks and mark
  coverage incomplete; observed duration excludes unobserved gaps.
- Context changes replace the current rule state without implying recovery.
  References for previously seen contexts can be reused while still cached.
- RSSI/PHY changes alone do not create service failure findings. Rules do not
  assign a causal domain or describe other clients' experience.

### Contextual reference

The reference key includes Agent (row scope), interface, SSID, band, declared
measurement location, target and applied profile. BSSID is retained by the probe
as evidence; it does not fragment references in this initial delivery. Wi-Fi
association availability uses interface/profile context so disappearance of the
SSID during disconnection does not mask an observed interruption.

By default, references need 30 distinct successful samples spanning 120s, under
the configured objective and outside alert/candidate states. They report median,
MAD, p95, sample count and establishment time. The upper boundary is the larger
of p95 plus a minimum meaningful delta and median plus
`max(6 × 1.4826 × MAD, 50% × median, minimum delta)`. Minimum deltas are 10ms LAN,
50ms DNS, 20ms Internet and 100ms application. They are initial deterministic
defaults for validation, not universal Wi-Fi performance recommendations.

Once ready, the reference freezes. It does not silently adapt to a degraded new
normal. A changed profile explicitly rebuilds it. The bounded cache retains at
most 32 references with at most 120 training samples each. Reference age is
shown, but this delivery has no automatic expiration or operator feedback loop;
an initially suboptimal environment under its objectives can become a reference.

## Persistence and deployment

Apply Alembic revision `0011` **before restarting the updated Server**:

```bash
set -a
source .env
set +a
(cd server && alembic upgrade head)
```

The new `agent_experience_monitors` table stores policy and bounded current rule
state/reference JSON. Restart Server and Agent and reload the frontend. Existing
Agent identity, recordings and diagnostic analysis remain compatible. No Agent
re-enrollment is needed. The local policy copy needs no SQLite migration.

## Validation and limits

Run `./scripts/release-gate.sh`. Labeled tests cover immediate interruption,
persistent degradation, a transient spike, tolerated oscillation, collection
errors, gaps, context/profile changes, replay, recovery hysteresis and frozen
reference contamination. Persistence is exercised across independent SQLite
sessions using the production service/model contracts; PostgreSQL DDL is checked
with Alembic offline generation. This is not a claim of hardware or PostgreSQL
concurrency validation. Browser QA uses simulated API responses for profile
editing, pending application, errors/recovery and responsive findings.

Current State publication can miss a result between snapshots or during Server
unavailability. Telemetry aggregates are not replayed as individual probe
outcomes, since doing so would manufacture evidence. Multi-Agent analysis and
Diagnostic Projects remain outside this roadmap. P0.4 adds a persistent individual
episode archive and opt-in fixed-window capture. The four-hour AX201 run remains
deferred and real Server-outage recovery remains pending.


Persistent individual history and opt-in trigger-window evidence are now described
in [CLIENT_EPISODES_AND_CAPTURE.md](CLIENT_EPISODES_AND_CAPTURE.md).
