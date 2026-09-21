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
