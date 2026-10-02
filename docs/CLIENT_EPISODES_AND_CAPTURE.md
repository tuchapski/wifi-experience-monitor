# P0.4 — persistent individual episodes and trigger-window evidence

Base: `a936960` (`feature/v2-foundation`). Upgrade Server schema to Alembic
`0012` before restarting Server and Agent. Continuous detection retains its
existing enable switch. Automatic capture is a separate opt-in, disabled by
default; existing profiles receive the new defaults without changing version.

## Episode identity and recovery

New confirmed rules create a durable episode scoped to one Agent, domain,
interface, SSID/band, location, target and profile. Findings for the same scope
share an episode; other domains remain independent. This grouping asserts no
cause. Opening readings, objectives and references are preserved independently
from the latest readings. Current State replays and browser polling cannot
create another episode or advance recovery.

Episodes progress through active, recovering, unknown and recovered. Evidence
older than 30 seconds or an offline Agent appears unknown. Reads do not rewrite
the stored history. New evidence after a gap records the missing interval;
observed degradation duration excludes gaps. Changed profile/context closes
open episodes as interrupted, with no inferred recovery. A confirmed recurrence
within 60 seconds reopens the same identity and clears its current recovery and
acknowledgment. Opening evidence and past transitions remain available. A later
recurrence creates a new episode.

Acknowledgment records review only. It never changes network recovery. Episode
history supports domain filtering, ten-row pages and individual bookmarks.
Detail shows confirmation readings, latest findings/references, profile/context,
transitions and collection coverage. Detail retains all transitions in storage,
returning the latest 200 with an explicit truncation indicator.

API:

- `GET /agents/{id}/experience/episodes?offset=0&limit=20&domain=local_network`
- `GET /agents/{id}/experience/episodes/{episode_id}`
- `POST /agents/{id}/experience/episodes/{episode_id}/ack`

Identifiers are checked against the requested Agent. Profile edits, episode
creation and manual collection starts serialize on the same Agent row.

## Automatic capture

Enable **Automatically capture individual episodes** under the client's
**Targets and performance objectives**. Defaults:

- 120 seconds before the first comparable bad observation in the episode.
- 300 seconds after its first confirmation trigger.
- 300 seconds between creating new automatic collections.

The window is fixed around confirmation: it does not extend indefinitely while
an episode remains active, or wait five minutes after final recovery. One
capture is requested per episode, including recurrences. A cooldown records a
skipped capture rather than silently dropping the episode.

An active individual collection is reused. Its start and deadline are preserved;
it may end before the requested window, which is shown as partial coverage. No
second collection is started. Legacy coordinated collections are left in place
and block automatic capture. New automatic captures have an absolute local
deadline and stop even while Server is unavailable. Delayed commands that
already expired fail without starting a new collection. Failed reused captures
do not mark the manual collection failed.

With the applied policy enabled, Agent stores normalized raw cycle metrics,
state observations (including unchanged probe outcomes), counter/survey deltas
and collection-error markers in its local SQLite buffer. Probe clocks, labels,
source and measurement metadata are retained; cached readings keep their own
clock. Retention covers requested pre-time plus confirmation delay plus 30s,
bounded at 630s, 2,000 cycles and 16 MiB of serialized evidence. Oversized cycles
are omitted and oldest evidence is evicted; coverage is explicit. Profile and
Agent/Server identity scope buffer exports. A clean restart retains comparable
buffered evidence; disabling capture clears the ring.

Buffer export, recording creation and successful command journal commit in one
SQLite transaction. After an ACK failure or restart, the same command returns
its saved result without duplicate export or restarting a completed recording.
Exact metric/event fingerprints deduplicate buffered evidence already captured
live, including unchanged cached probe outcomes. New exports fail if the durable
recording outbox already exceeds 128 MiB. The existing recording outbox retries
batches and manifests after connectivity returns.

## Coverage and limits

A completed manifest computes actual cycle timestamps, missing intervals,
collection-error cycle counts and whether the requested window is covered.
Coverage requires a complete manifest and cycle bounds/intervals within three
configured sampling intervals (at least 3s). A missing cycle buffer, an early
manual stop, eviction, Agent downtime or incomplete sync remains visible as
partial. Collection errors are counted separately from time coverage. A new
manifest recomputes coverage after late batches. Late evidence never invents
an episode recovery or replays missed detector outcomes.

Pre-trigger RF scan records are not buffered by this delivery. The existing RF
pipeline associates scans while a recording is active. Changing capture policy
is not a request to increase RF scan frequency. Buffered `state.observation`
events expose original states, but existing legacy analyses still use their
original `state.initial`/`state.changed` rules and recording start boundary. In a
reused manual recording, backfilled measurements before that original start are
stored but may be outside the legacy analysis window. Use episode coverage and
original timestamps when inspecting such evidence.

The detector still sees Current State publications, not every raw probe during
Server outages. Automatic episode capture cannot be triggered until Server
receives a confirming observation. Real hardware and long outage/restart
validation remain necessary; automated tests use SQLite and mocked HTTP/browser
responses. PostgreSQL migration validation includes generated offline SQL.
