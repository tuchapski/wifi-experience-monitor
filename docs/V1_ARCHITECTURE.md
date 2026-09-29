# V1 Architecture and Diagnostic Model

This document is the canonical technical description of the current V1 runtime.
It describes the `server/`, `agent/` and active `frontend/` code paths. Historical
monolith code under `src/wem/` is retained for compatibility and is not the
runtime architecture described here.

## Runtime topology

```text
                      operator
                         │
                         ▼
                 ┌───────────────┐
                 │   Frontend    │
                 │ React / Vite  │
                 └───────┬───────┘
                         │ HTTP
                         ▼
┌───────────────┐  HTTP  ┌──────────────────────────┐
│ Linux Agent   ├───────►│ Server / FastAPI         │
│ autonomous    │        │ PostgreSQL               │
│ sensor        │◄───────┤ Agent commands           │
└───────┬───────┘        │ recording analysis       │
        │                └──────────────────────────┘
        │
        ├─ nl80211 / iw
        ├─ IP routing / gateway
        ├─ DNS resolver
        ├─ ICMP probes
        └─ HTTPS transaction probes
```

The Agent is the measurement plane. The Server is the control, persistence and
analysis plane. The Frontend consumes Server APIs; it does not collect Wi-Fi
measurements directly.

## Agent

The Agent package is `agent/src/wifi_agent`. `wifi-agent run` owns the long-lived
runtime loop.

At startup the Agent loads `AgentSettings` from environment variables and opens
`WEM_AGENT_DATA_DIR/agent.db`. If no identity exists, the run path enrolls with the
Server and stores the returned Agent ID/token. If the configured Server URL differs
from the URL stored in the identity, the Agent exits and requires an explicit
`wifi-agent enroll --force`.

The runtime continuously performs four independent responsibilities:

1. heartbeat and command retrieval;
2. current-state collection/publication;
3. rolling telemetry aggregation/spooling/synchronization;
4. diagnostic recording capture/synchronization when commanded.

Synthetic gateway, DNS, Internet and HTTPS observations are cached only for their
configured freshness window before being included in Current State. Recording
capture receives the raw observations generated while the collection is active.

### Sensor capability truth

Enrollment capabilities describe tools/prerequisites discovered by the Agent.
They are inventory, not proof that a metric is currently measurable.

Runtime Sensor Readiness is derived from current observations. For example,
channel-utilization readiness depends on survey data actually exposed by the
driver. A missing runtime measurement is represented as unavailable/degraded
rather than inferred from enrollment capability.

## Server

The Server package is `server/src/wifi_server`. `wifi-server` starts FastAPI and
the automatic analysis-recovery worker.

The Server owns:

- Agent enrollment, token authentication and online/offline status;
- latest Current State per Agent;
- bounded rolling telemetry;
- recording lifecycle and Agent commands;
- recording metrics/events/manifests;
- diagnostic projects and project runs;
- deterministic recording analysis;
- focused metric comparison and evidence correlation;
- standalone recording HTML reports.

The main API families are `/api/v1/agents`, `/api/v1/recordings` and
`/api/v1/diagnostic-projects`.

## Frontend

The active entry point is `frontend/src/main.tsx`, which renders
`AgentWorkspace`.

Primary navigation has two operational sections:

- **Agents** for realtime state, Experience Path, Link Score, rolling telemetry,
  Sensor Readiness and Agent inventory;
- **Diagnostics** for active collections, individual Datasets, multi-Agent
  Projects and Recording Detail.

A global collection indicator remains visible whenever any Agent has an active
Recording and links back to the Diagnostics activity section.

## Data and lifecycle vocabulary

### Current State

The latest direct Agent observation set. It is designed for realtime visibility,
not retrospective root-cause analysis. The Frontend treats stale state as stale
instead of presenting it as current.

### Rolling telemetry

Aggregated time-series observations retained by the Server for recent operational
context. This is distinct from an immutable diagnostic Recording.

### Collection

The operator-facing activity. Starting a Collection asks the Server to create a
Recording and queues an Agent command. Stopping it requests the inverse command.
Projects may start coordinated Collections on multiple Agents.

### Recording

The technical persisted capture object. Typical lifecycle states are `created`,
`recording`, `stopping`, `completed`, `failed` or `cancelled`.

The Agent uploads raw recording batches and, when the capture ends, a manifest.
The Server tracks synchronization independently from recording lifecycle status.

### Dataset

The investigation-facing representation of a historical Recording. Diagnostics
keeps active Collections visually separate from historical Datasets.

### Project

A coordination object that starts one Recording per selected Agent/position.
Analysis remains per Agent/Recording. V1 does not synthesize a single project-wide
root-cause verdict.

## Recording analysis

A completed and fully synchronized Recording is eligible for deterministic
analysis. The Server automatically schedules analysis after accepting the final
manifest and also runs a recovery worker for eligible recordings that lack a
current analysis.

The analysis model deliberately keeps several outputs separate.

### Threshold finding

A versioned heuristic/rule result with severity, evidence and a suggested next
action. A Recording can have zero threshold findings and still contain diagnostic
episodes or other useful evidence.

### Degraded window

A sustained Wi-Fi interval where configured evidence conditions overlap. It is
used as an investigation interval and carries measurements/evidence observed
inside that window.

### Diagnostic episode

A sustained deterioration relative to the recording baseline. Episodes may be
single-domain or cross-layer and identify the earliest observed evidence domain.
That ordering is descriptive and not causal attribution.

### Evidence domain

Every focused comparison maps evidence into one of five domains:

```text
wifi_rf
local_network
dns
internet
application
```

These domains create a consistent path from the client radio through the
application transaction.

### Probable domain

Focused evidence correlation may return a `Probable domain` using the
`earliest-supported-domain-v1` method. Its status may be probable, ambiguous,
insufficient evidence or not observed.

`Probable domain` is an evidence assessment, not a proven root cause. Temporal
proximity between a metric degradation and a state change also does not establish
causality.

## Recording Detail information architecture

Recording Detail is organized for progressive disclosure:

```text
Recording identity / lifecycle
        ↓
Diagnostic overview
        ↓
Investigation Timeline
        ↓
Diagnostic Evidence (when an interval is focused)
        ↓
Compact Diagnostic Metrics
        ↓
Full telemetry
        ↓
State events
        ↓
Recording metadata
```

Compact Diagnostic Metrics prioritize RSSI, retries, TX failures, channel
utilization, gateway latency/loss, DNS latency, Internet latency/loss and HTTPS
total/TTFB. When a diagnostic interval is focused, the cards reuse the raw
comparison API to show Before/During/After values and the interval on the
sparkline. `Show all metrics` expands the compact layer; Full telemetry remains
the complete technical view.

## Persistence

### Server

`SERVER_DATABASE_URL` is required and the current development configuration uses
PostgreSQL. `WEM_RECORDING_STORAGE_ROOT` controls recording artifact storage.

Alembic migrations live under `server/alembic`; apply them with:

```bash
(cd server && alembic upgrade head)
```

### Agent

The systemd installation uses:

```text
/opt/wifi-experience-agent/venv
/etc/wifi-experience-agent/agent.env
/var/lib/wifi-experience-agent/agent.db
```

The SQLite Agent database persists identity, token, local telemetry spool and
recording state. Importing an existing data directory is the supported way to
preserve a development Agent identity during conversion to the system service.

## Autonomous system service

`agent/install.sh` creates a dedicated `wifi-experience-agent` user and installs
`wifi-experience-agent.service`.

The service does not run as root. Its capability bounding set and ambient
capabilities contain `CAP_NET_ADMIN` and `CAP_NET_RAW`, required for the current
low-level network observation/probe model. The unit enables restart-on-failure
and starts with `multi-user.target`.

See `agent/deploy/README.md` for installation and operational commands.

## Release discipline

`scripts/release-gate.sh` is the local V1 quality gate. It verifies shell syntax,
Python lint/formatting, Server tests, Agent tests, legacy compatibility tests,
Frontend tests/lint/build and Git whitespace.

The compatibility suite exists because legacy code is still versioned. Passing
those tests does not make the legacy monolith the V1 runtime path.

## V1 limitations and interpretation rules

The current V1 design is evidence-first and intentionally conservative.

- Missing measurements remain unavailable rather than being treated as healthy or
  zero.
- Enrollment capability does not imply runtime measurement availability.
- Current State is realtime observation, not deep diagnostic correlation.
- Threshold findings and diagnostic episodes are independent analysis products.
- Earliest observed domain is temporal context.
- Probable domain is an evidence assessment.
- Temporal correlation does not prove causality.
- Per-Agent project analyses must not be combined into an unsupported shared root
  cause.
- The current deployment model is oriented to trusted/local environments rather
  than a hardened multi-tenant control plane.
