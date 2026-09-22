# Wi-Fi Experience Monitor

Linux-based Wi-Fi and Digital Experience Monitoring platform.

The project monitors the network from the perspective of an end user and
collects Wi-Fi, RF, connectivity, performance and application experience
metrics.

## Initial scope

- Linux sensor health
- Wi-Fi metrics
- RF metrics
- Network connectivity tests
- DNS tests
- Internet tests
- HTTP/HTTPS synthetic tests
- Historical metrics
- Incident detection
- Diagnostic engine
- Web dashboard

## Supported environment

Initial development target:

- Linux
- NetworkManager
- nl80211 / iw
- Intel iwlwifi
- Wi-Fi as primary network connection

## Development

Create the environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

```

## Start the application

```bash
source .venv/bin/activate
python -m wem.main --database data/wem.db
```

This starts the API on 127.0.0.1:8000 with monitoring stopped. Do not launch
an additional console collector or a second API process against the same database.
The former `--interface` and `--interval` CLI arguments are replaced by the dashboard controls.

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173, select a wireless interface and click Start Monitoring.
The backend rechecks that the interface is available before starting. Stop ends
collection; each new Start creates a new runtime and resets metric deltas.
Historical samples remain stored but are not displayed as a current session.

## Versioned test profiles

On database initialization, the backend creates and activates `Default v1` when
no profile exists. Its targets, five-second cadence and diagnostic thresholds
match the behavior used before profiles were introduced. Re-running the
initialization is idempotent and does not replace existing profiles.

Profile configuration is validated and stored as immutable JSON versions in
SQLite. Updating a profile creates a new version; updating the active profile
also activates that new version. Activating another enabled profile atomically
deactivates the previous one. An active profile must be replaced before it can
be disabled.

The backend exposes `GET/POST /profiles`, `GET/PUT /profiles/{id}`,
`GET /profiles/active`, `POST /profiles/{id}/activate` and version-history
endpoints below `/profiles/{id}/versions`.

Each monitoring start pins the then-active immutable profile version in a
persistent session. Wi-Fi sampling follows the profile cadence, while enabled
synthetic tests run independently at their configured intervals. Cached results
remain visible with `fresh: false`, `observed_at` and `age_seconds`, but do not
advance incident confirmation or recovery counters. Profile changes made during
a running session apply only after monitoring is restarted.

An enabled synthetic-test interval must be equal to or an integer multiple of
the Wi-Fi sampling interval. This keeps snapshot timing deterministic while
allowing cadences such as 5, 10, 30 and 60 seconds. `/sensor/status` reports the
session, profile and exact profile-version identifiers used by the runtime.

The dashboard **Settings** tab manages these profiles without editing JSON by
hand. It supports creating profiles, saving immutable revisions, activating an
enabled profile and inspecting every stored version. When monitoring is already
running, the page makes clear that changes apply only after the sensor is
stopped and started again.

## NetworkManager event timing

Connection-cycle timing uses NetworkManager device `StateChanged` signals from
the system D-Bus when `gdbus` is available. The sensor observes those signals
read-only; it does not change NetworkManager configuration. Activation start,
the boundary where layer-2 activation has completed, and the boundary where IP
configuration has completed can therefore use event timestamps instead of the
next periodic sample.

These timestamps describe NetworkManager phase transitions, not the exact time
of an 802.11 management frame. Authentication/authorization reported by `iw`,
gateway reachability, DNS and final network readiness remain sample-based when
no stage-specific event exists. The dashboard exposes the timing source for each
stage and the D-Bus monitor status. If D-Bus monitoring is unavailable or exits,
the existing sampling tracker continues to operate and records the reason.

The IPv4 stage intentionally does not claim that DHCP was used. NetworkManager's
IP configuration phase also covers static addressing; the UI therefore labels
that stage **IPv4 address**.

## Connection-cycle SLO

Each test profile also defines a rolling connection-cycle SLO. Only unique cycles
with a measured network-ready duration enter the window; pre-existing sessions,
in-progress cycles and unknown durations never become zero-valued samples. The
default policy evaluates P95 after at least five measured cycles in a 20-cycle
window, warning at 8000 ms and becoming critical at 15000 ms.

The incident domain advances only when a new measurable cycle arrives. Repeated
snapshots of the same cycle therefore cannot satisfy incident confirmation or
recovery counters. Threshold changes remain pinned to the profile version selected
when monitoring starts.

The connection-cycle SLO also evaluates Association, Authentication, IPv4 address,
Gateway and DNS milestone P95 values independently. These values are elapsed time
from the observed connection start to each milestone, not isolated protocol-stage
durations. This distinction is important because NetworkManager D-Bus timestamps and
sample-derived observations can use different timing sources. Each milestone keeps
its own rolling sample set and stable incident code, so fresh Association evidence
cannot resolve a DNS-stage incident. The existing end-to-end P95 remains the Network
Ready SLO.

## Adaptive same-SSID baseline

The sensor can compare fresh measurements with its own recent history for the same
interface and SSID. The reference model uses the median and median absolute deviation
(MAD), so isolated historical spikes have less influence than they would with a mean
and standard deviation. Metric-specific scale floors prevent a zero or near-zero MAD
from turning negligible changes into anomalies.

RSSI, TX retries, gateway/Internet latency, DNS, HTTPS and connection-cycle P95 are
evaluated independently when they have enough reference samples. Cached synthetic-test
results are not relearned as new measurements, and connection-cycle P95 enters the
baseline only when a new measurable cycle updates that rolling statistic. Missing or
insufficient history remains explicitly unavailable rather than being treated as zero.

Adaptive findings complement the absolute thresholds in the active profile; they do
not replace them. Warning/critical deviation multipliers, lookback and sample limits are
versioned with the profile. Baseline incidents use stable per-metric codes and only
advance confirmation or recovery when that specific metric has fresh evidence.

## Synthetic service SLA/SLO

Gateway, Internet, DNS and HTTPS tests also feed a profile-versioned rolling SLO.
Only fresh test executions enter the window. Availability uses definitive `passed`
and `failed` outcomes; sensor-side collection `error` results are tracked separately
and are not silently converted into service outages. Cached results never advance the
window or incident confirmation.

Latency P95 uses successful measurements. Gateway and Internet additionally evaluate
packet-loss P95. The default policy uses a 60-execution window and waits for 20
definitive samples before evaluating a dimension. Availability, tail-latency and
packet-loss thresholds remain independent from the existing single-sample diagnostic
limits.

History and HTML reports summarize fresh executions for the selected period with
availability, failure/error counts and latency/loss percentiles. Those historical
figures are observational; rolling incident compliance remains tied to the immutable
profile version selected when monitoring starts.

## Evidence correlation

The correlation engine combines existing diagnostic findings instead of inventing a
new measurement source. Current findings, rolling service SLOs, adaptive-baseline
deviations and connection-cycle stage SLOs are treated as independent evidence
classes and mapped to Wi-Fi, local-network, DNS, Internet or application domains.
Healthy upstream observations may add isolation evidence, for example a reachable
gateway supporting an Internet-path hypothesis or successful DNS/Internet checks
supporting isolation toward the HTTPS application target.

Support is qualitative and deterministic: `strong` requires converging evidence
classes or a critical current failure with isolation evidence; `moderate` requires a
critical signal, repeated evidence, or a current signal with isolation; otherwise the
hypothesis remains `weak`. If multiple domains share the highest support level the
result is explicitly `ambiguous` and no primary domain is selected. Sensor collection
gaps are retained as limitations, and the assessment never claims a proven root cause.
The correlation result is stored in snapshot JSON and does not create duplicate
incidents; objective findings and SLO violations remain the incident sources.

## Experience episodes

The incident view also derives higher-level experience episodes without adding a
second persistence model. Incident intervals that overlap, or whose gap is at most
120 seconds, are grouped into one operational episode. The original incidents remain
the immutable evidence and are still shown individually.

Stored warning/critical snapshots inside each episode are inspected for correlation
results. A primary episode domain is assigned only when all correlated snapshots in
that episode agree on the same domain. If multiple correlated domains occur, the
episode is marked `mixed`; if no correlated snapshot exists, correlation remains
`unavailable`. Clearing ended incident history therefore also removes the derived
ended episodes, while active intervals remain visible.

## Environment-change events

Each comparable sample is checked for radio and association changes. The sensor
records changes to SSID, BSSID, channel, frequency, operating channel width,
TX/RX PHY mode and association state. The first sample and transitions involving
unknown values do not create an event, avoiding false changes after a collector
failure.

Environment changes are stored inside the snapshot JSON and returned with the
time-range history response. The dashboard renders them as red vertical markers
and lists the exact sample time and old/new values. A BSSID change is evidence of
a different access point; it does not by itself prove a roaming problem. Channel,
frequency, width and PHY changes may be caused by AP steering, channel selection,
band changes or renegotiation and should be correlated with RSSI, retries and
latency.

The event list is bounded by the selected history window and interface. Old
snapshots created before this feature simply have no events and remain valid.


## Calibration and diagnostic evidence

Connectivity results include `tests` entries with a status, reason and scope:
`passed`, `failed`, `error` (collection failed), or `skipped` (not executed).
Missing measurements remain null, including failed ping execution without usable
statistics. No gateway means the gateway test is skipped, not failed.

DNS and HTTPS use the host resolver/routing and are explicitly labeled as host
checks; they do not prove connectivity through the selected Wi-Fi interface.
ICMP failure alone generates a warning, not a general Internet outage diagnosis.
An absent, unverified, blocked or disconnected interface skips synthetic tests.

Calibration exposes each observed or unavailable value. Missing checks make the
assessment inconclusive; calibration does not certify that every local cause has
been excluded. RF-kill evidence is read for the selected interface's physical radio.

Incomplete diagnostic samples do not count toward incident recovery. This is
conservative: outstanding sensor checks can keep incidents open even when other
measurements have recovered. Existing historical JSON remains readable and old
samples without test metadata are shown as unavailable.

## Wi-Fi link metrics

The dashboard includes a radio/link panel with current and driver-averaged RSSI,
beacon signal, channel/frequency, operating width, TX power and association duration.
The TX/RX table exposes reported PHY rate, PHY mode, MCS, NSS, rate width and HT/VHT
short GI. Missing metadata remains unavailable; NSS is not inferred from a rate.
PHY rate is not application throughput.

Operating width is collected from interface info and is kept separate from the
width reported for TX and RX. Link measurements survive an empty/partial station
dump; when multiple peers are reported, only the associated BSSID is used.

Retransmission details distinguish cumulative driver counters from changes between
samples. Retry counts per 100 TX packets may exceed 100 and do not measure the
percentage of distinct packets retried. Zero packet activity leaves ratios
unavailable. Interface/AP changes, unconfirmed association, counter resets and a
restarted association duration invalidate comparisons until comparable samples
are available again. These checks cannot detect every unreported driver reset.

New fields are stored in the existing snapshot JSON; no database reset or schema
migration is required. Older snapshots may lack the new directional width fields.

## HTML reports

The historical dashboard can open an HTML report for the selected interface and
period through `GET /reports/html`. The report is self-contained: it includes
inline SVG charts, stored sample counts, environment changes, incidents and
interpretation limitations. It can be printed to PDF from the browser without
requiring a server-side PDF dependency.

History buckets also expose P50, P95 and P99 for every numeric metric. Percentiles
are calculated from the raw readings inside each bucket using linear interpolation;
they are not estimated from bucket averages. P95/P99 help expose short spikes that
an average can hide. A percentile is unavailable when the bucket has no valid
readings, and values from different interfaces are never combined.

## Evidence-based recommendations

Each current snapshot can include a `recommendations` list derived from diagnostic
findings, calibration state and environment-change events. The dashboard renders
these as bounded next actions with a severity, rationale and the exact evidence
that triggered the suggestion.

Recommendations cover common Wi-Fi, gateway, DNS, Internet and HTTPS conditions,
including low signal, retransmissions, packet loss, high latency, failed synthetic
tests, power saving and collection errors. A BSSID change or roam suggests
correlating metrics before and after the transition; it does not claim that roaming
is the root cause. Unknown diagnostic codes are not turned into speculative advice.

The recommendations are guidance, not an automated remediation or proof of root
cause. Missing or incomplete measurements remain visible through calibration and
collection-error evidence.

## Historical period comparison

The historical dashboard compares the selected window with the immediately
preceding window of the same duration and interface. It reports the current and
previous averages for RSSI, gateway and Internet latency, packet loss and TX
retries, along with the signed delta.

The comparison uses all available raw readings in each period rather than the
visual bucket averages. A positive RSSI delta is generally better because the
value is less negative; lower latency, packet loss and retry deltas are generally
better. Missing readings do not become zero and are shown as unavailable. The
comparison is descriptive evidence, not a causal attribution.

## Incident intervals and history cleanup

Incident history is presented as time intervals. Each entry exposes its start,
optional end and calculated duration; an open incident has no end timestamp and
its duration is calculated up to the current time. The dashboard no longer uses
`active` or `resolved` as the history label, although the runtime still tracks
open findings internally so that an interval can be closed after recovery.

The Incident timeline chart shows each interval as a colored bar: critical,
warning or informational. The tooltip includes the incident code, duration and
evidence message. The **Clear history** action deletes only ended intervals and
preserves currently open incidents. This prevents a cleanup action from losing
the interval that is still being measured.

## Optional RF survey telemetry

The RF tab displays driver noise, estimated SNR, primary-channel busy time and
radio RX/TX time from `iw dev <selected-interface> survey dump`. This is a
read-only query: it does not scan, disconnect, change channels or enable monitor
mode. Association and frequency must be known; exactly one in-use survey entry
must match the observed frequency. Optional errors and unsupported drivers are
shown in the RF panel, not treated as connectivity failures.

Survey support is driver-dependent, including on Intel AX201/iwlwifi. Missing
noise or counters remain null. SNR is only estimated when RSSI and a usable
negative noise reading exist. Zero/nonnegative noise readings are conservatively
discarded. RSSI and noise can have different averaging windows.

Occupancy is `100 * delta(busy_ms) / delta(active_ms)`, never a lifetime ratio.
RX and TX percentages use the same denominator. Comparable samples require the
same interface, association, known frequency and known width. First samples,
resets, unavailable counters, zero active-time deltas and deltas larger than
active time do not produce fabricated percentages. Partial counters are allowed.
Busy refers to the primary channel, not the full bonded bandwidth. RX/TX and
active time may be radio-wide depending on the driver; percentages are not
additive. These observations cannot identify non-Wi-Fi interferers.

Raw survey values and calculated deltas are stored in snapshot JSON and exposed
by the snapshot API without a database migration. Existing historical charts and
HTML reports remain unchanged in this increment. No new automatic incidents or
RF thresholds are introduced until hardware measurements have been validated.

## Explainable experience score (experience-v1)

The Dashboard shows a 0–100 score separately from diagnostic status and incidents.
This is a project heuristic for the current sample, not a vendor score, SLA,
statistical confidence estimate or proof of root cause. Policy rules live in
`src/wem/analysis/experience.py`; change the version when changing weights or
thresholds. No new probes, automatic remediations or incident rules are added.

| Component | Global weight | Internal metric weights |
| --- | ---: | --- |
| Wi-Fi | 30% | RSSI 40%, retries 40%, TX failures 20% |
| Gateway ICMP | 20% | Latency 40%, packet loss 60% |
| Internet target ICMP | 20% | Latency 40%, packet loss 60% |
| DNS | 15% | Resolution time after successful test 100% |
| HTTPS | 15% | Response time after successful test 100% |

Each numeric metric uses linear interpolation between the following
`reading → score` anchors (outside anchors, the nearest endpoint score applies
only to valid measurements):

| Metric | Anchors |
| --- | --- |
| RSSI (dBm) | -90 → 0; -82 → 40; -75 → 70; -67 → 100 |
| Retries / 100 TX | 0 → 100; 10 → 100; 20 → 70; 50 → 20; 100 → 0 |
| Failures / 100 TX | 0 → 100; 1 → 85; 5 → 20; 10 → 0 |
| Gateway latency (ms) | 0 → 100; 10 → 100; 50 → 70; 150 → 20; 500 → 0 |
| External latency (ms) | 0 → 100; 50 → 100; 150 → 70; 300 → 20; 1000 → 0 |
| ICMP packet loss (%) | 0 → 100; 1 → 90; 5 → 60; 20 → 10; 100 → 0 |
| DNS time (ms) | 0 → 100; 50 → 100; 250 → 70; 1000 → 20; 3000 → 0 |
| HTTPS time (ms) | 0 → 100; 300 → 100; 1000 → 70; 3000 → 20; 5000 → 0 |

A confirmed test failure overrides that component with score zero, without
inventing a latency/loss measurement. Confirmed Wi-Fi disassociation similarly
scores Wi-Fi zero; skipped downstream probes remain unavailable, not failed.
ICMP failures only describe the configured ICMP target; the Dashboard retains
this warning and highlights failures even if the weighted average remains high.
Explicit test outcome and success flag must agree. Errors, skipped tests, absent
outcomes and invalid/non-finite values are excluded, never converted to zero.

RSSI requires confirmed association. Retry/failure ratios require a valid
interval with positive TX packets and no reset/roam/incomparability flag. No
traffic does not imply perfect packet delivery. RF survey support is not scored.

Component coverage is the sum of its available internal metric weights.
Global coverage is `sum(base_weight * component_coverage / 100)`.
The available weight of each component is that same product; effective weights
are renormalized over the total available weight. Component scores are weighted
averages of available metrics; the global score is the weighted average of
available component scores. Small rounding differences in displayed sums are
expected. Missing components are shown as unavailable with no penalty.

The global score requires **at least 70% weighted coverage**, usable Wi-Fi
evidence and at least two connectivity components. Otherwise it is null while
individual evidence remains visible. Partial coverage, incomplete calibration
or collection errors mark the result **provisional**, even at 100/100. Full
coverage measures completeness, not correctness of the network; a complete
assessment can include failed tests. Partial and complete scores should not
be compared without checking their evidence mix.

Example: RSSI -75 dBm scores 70; with good retry/failure ratios, Wi-Fi scores 88
and contributes 26.4 of its possible 30 points. If everything else scores 100,
the global score is 96.4. On a first sample without counter deltas, only Wi-Fi
RSSI contributes: total coverage is 82% if all connectivity tests are valid.
Such a score is explicitly provisional.

The version, score, weights, evidence, penalties and coverage are persisted in
snapshot JSON and returned by `/snapshot/latest`, without a schema migration.
Older snapshots retain no score and are not recalculated. Historical score
charts and score sections in HTML reports are outside this increment.

Validation: run the regular Python checks, then `cd frontend && npm test`,
`npm run build` and `npm run lint`. Frontend tests verify server-rendered panel
states; they do not replace an interactive browser/hardware check.
