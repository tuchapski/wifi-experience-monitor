# P0.1-G — Recording RF summaries

The recording RF panel includes a summary of **all stored RF scans**, served by
`GET /api/v1/recordings/{recording_id}/rf/summary`. The timeline and snapshot table
continue to show the latest 2,000 scans. The summary query streams rows in batches
and buffers one scan at a time, plus the unique BSSID and SSID sets.

## Meaning of the summary

- Visible neighbors exclude BSS marked associated. BSS counts are not physical AP counts.
- Same-channel neighbors share the associated BSS's primary frequency in MHz.
  Equal channel numbers in different bands do not match. Channel width overlap is not evaluated.
- Same-SSID neighbors require an exact, nonempty SSID match with one observed associated BSS.
- Strong neighbors have RSSI >= -70 dBm. A scan is comparable only when every
  neighbor has a finite RSSI; an empty neighborhood has a known count of zero.
- Stronger same-SSID alternatives compare the strongest observed alternative RSSI
  with the associated BSS in that scan. All alternative RSSI readings must be known.
  The percentage uses comparable scans, not all scans; equal RSSI is not stronger.
- BSSID/frequency changes require consecutive scans on the same interface with
  exactly one associated BSS. Missing or ambiguous association breaks continuity.
- Neighborhood changes count visible BSSID set differences between consecutive
  scans on the same interface. Appearances/disappearances do not establish physical topology changes.

Every statistical card shows its valid-scan denominator. Missing comparisons return
`null`, rendered as a dash, rather than zero. Averages and percentages are per scan,
not time weighted. The observed window, association coverage and maximum scan gap
describe evidence availability, not completeness of the recording or continuous RF coverage.
Active recordings remain provisional as scans synchronize.

No congestion, interference, roaming fault or causal diagnosis is inferred.
Noise, survey and airtime remain unavailable on the current AX201 collection path.
No database migration or Agent changes are required for this step.

## Validation

Run `./scripts/release-gate.sh`. Focused checks:

```bash
python -m pytest server/tests/test_recording_rf_summary.py server/tests/test_recording_rf_timeline.py
(cd frontend && npm test && npm run lint && npm run build)
```

Coverage includes empty scans, unknown/ambiguous association, hidden SSIDs,
missing RSSI, channel-number collisions between bands, interface changes,
real SQL filtering/ordering, HTTP serialization/404 and a peak before the latest
2,000 scans. P0.1-H remains the hardware and long-running validation step,
including the effect of active scans on client traffic.
