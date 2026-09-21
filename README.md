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
