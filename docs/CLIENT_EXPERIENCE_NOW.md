# P0.2 — Individual client experience now

Base: `a9fea9c` on `feature/v2-foundation`.

The Agent detail now presents **Experience now** for one client. Wi-Fi association,
LAN reachability, system DNS resolution, Internet ICMP and the configured HTTPS
target have independent outcomes and expandable evidence. A failed application
remains visible even when the other tests succeeded. Partial ICMP replies are
reported as observed degradation; the UI assigns no causal diagnosis.

## Observation contract

Current State includes optional `measurement_metadata`, keyed by full metric
name. Each record carries its original `observed_at`, `source`, unit,
`sample_count`, optional `interval_seconds`, interface/target labels and nullable
`profile_version`. The current environment-configured runtime does not invent a
profile version; this field remains null until a version is actually supplied.

The snapshot timestamp does not renew the clocks of cached probes. The sample
count is the count of the current observation, not the number of ICMP packets;
packet denominators have separate `*_packets_sent` and `*_packets_received`
fields. Existing ping min/max RTT observations are preserved.

Synthetic workers emit `network.<test>_collection_error`. A failed worker or tool
replaces cached results for that test; a successful subsequent execution clears
the error. A service failure remains a boolean outcome, while a tool error
produces unknown service availability. Slow probes continue in background threads.

No database migration is required: metadata uses the existing Current State JSON
storage. Older Agents and stored snapshots remain readable. Without original
observation clocks their outcomes are displayed as partial evidence.

## API and interpretation

`GET /api/v1/agents/{agent_id}/experience` returns a versioned evaluation with five
domains, measurements, targets, current-outcome coverage, collection warnings and
limitations. An unknown Agent returns 404. An Agent without Current State returns
200 with unavailable outcomes.

States: `observed_ok`, `degraded`, `failure`, `partial`, `unavailable`, `stale`,
`collection_error`. Green availability requires an explicit boolean outcome and
fresh evidence; a latency reading alone cannot establish success.

Freshness uses the Server evaluation clock, each metric's own clock and online
status from the configured heartbeat window. The maximum observation age is
30 seconds with 5 seconds of tolerated forward clock difference. Non-finite
values, incompatible interface/default-gateway context and inconsistent clocks
cannot certify availability. Browser views also expire observations as time
passes without a response, using elapsed monotonic time after receipt.

Coverage is the count of valid current outcomes among these five domains, including
observed failures. It is not a measure of WLAN coverage or confidence in root
cause. **Tests responding** means availability of the configured targets;
latency objectives, historical baselines and sustained anomaly detection belong
to P0.3. The existing Wi-Fi link score retains its separate meaning and weights.

## Individual navigation

Diagnostics shows recordings for the selected client. With one enrolled Agent,
that client is selected automatically; with several, selection is explicit.
The Projects tab is removed, and project/coordinated collection APIs are not called
from the active Diagnostics view. The collection indicator is scoped to the
selected client and excludes project recordings.
The collection form shares the selected client and waits for its active-recording
list before enabling a new collection.

Previously stored projects, their recordings and backend APIs are retained for
compatibility. A legacy active recording still prevents another concurrent
recording on the same Agent. Individual recording bookmarks and deletion,
record-again, reports and RF investigation remain available.

## Validation and operation

Run `./scripts/release-gate.sh`. Focused tests cover per-observation clocks,
worker errors/cache recovery, packet denominators/extremes, persistence, legacy
payloads, invalid timestamps/context, loss/failure separation, application
failure precedence, API behavior and browser evidence expiry.

After applying the patch, restart Server and Agent so the new API and metadata
publisher are loaded. Reload the frontend. Existing identity and recordings are
reused; do not enroll the Agent again. Hardware validation of four hours remains
deferred, and real Server-outage recovery remains a separate pending validation.
