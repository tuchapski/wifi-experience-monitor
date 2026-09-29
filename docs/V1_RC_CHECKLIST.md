# V1 Release Candidate Checklist

Target tag: `v1.0.0-rc.1`

This checklist is the final V1 RC validation. It is intentionally blocker-focused:
do not add features while running it.

## 1. Source state

- [ ] `feature/network-collector` contains all intended V1 commits.
- [ ] `git status` is clean before the final tag.
- [ ] Active components report the RC version:
  - Server Python package: `1.0.0rc1`
  - Agent Python package: `1.0.0rc1`
  - Frontend package: `1.0.0-rc.1`

## 2. Automated quality gate

From the repository root:

```bash
./scripts/release-gate.sh
```

Expected: all 11 checks pass.

## 3. Database migration state

With the development environment loaded and PostgreSQL running:

```bash
cd ~/wifi-experience-monitor
source .venv/bin/activate
set -a
source .env
set +a

docker compose up -d postgres
(cd server && alembic upgrade head)
(cd server && alembic current)
(cd server && alembic heads)
```

`alembic current` must identify the same head revision reported by
`alembic heads`.

## 4. Server smoke test

Start the Server:

```bash
wifi-server
```

From another terminal:

```bash
curl http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok"}
```

Also verify the OpenAPI metadata reports Server version `1.0.0rc1`.

## 5. Autonomous Agent

The system service must be enabled and active:

```bash
systemctl is-enabled wifi-experience-agent
systemctl is-active wifi-experience-agent
sudo systemctl status wifi-experience-agent --no-pager
```

Expected: `enabled` and `active`.

Verify the Agent is not running as root:

```bash
ps -eo user,pid,cmd | grep '[w]ifi-agent'
```

Verify recent heartbeat/state activity:

```bash
sudo journalctl -u wifi-experience-agent -n 100 --no-pager
```

## 6. Reboot recovery

Reboot the sensor host without manually starting `wifi-agent` afterward.

After boot:

```bash
systemctl is-active wifi-experience-agent
sudo journalctl -u wifi-experience-agent -b --no-pager
```

The same Agent identity must return Online in the Frontend.

## 7. Realtime functional smoke test

In Agent Detail verify:

- [ ] Agent status is Online.
- [ ] Current State is fresh.
- [ ] SSID/BSSID/channel/RSSI are coherent with the host connection.
- [ ] Experience Path renders Wi-Fi, Gateway, DNS, Internet and Application.
- [ ] Missing driver-dependent RF measurements remain unavailable rather than zero.
- [ ] Rolling telemetry receives new points.
- [ ] Sensor Readiness reflects runtime truth rather than advertised capability alone.

## 8. Individual collection lifecycle

Run one complete collection:

- [ ] Start from Diagnostics.
- [ ] Global collection indicator appears.
- [ ] Now collecting shows the active Recording.
- [ ] Metrics/events counters advance.
- [ ] Stop works.
- [ ] Recording completes and synchronization becomes complete.
- [ ] The completed Recording appears as a Dataset.
- [ ] Automatic analysis becomes available.
- [ ] Recording Detail loads Diagnostic overview, Timeline, Diagnostic Metrics and Full telemetry.

Then run `Collect again` from that Dataset:

- [ ] A new Recording appears immediately in Now collecting.
- [ ] The original button does not remain stuck on `Starting…`.

## 9. Focused diagnostic evidence

For a Dataset containing a diagnostic interval:

- [ ] Selecting a degraded window or diagnostic episode focuses Diagnostic Evidence.
- [ ] Compact Diagnostic Metrics show the focused interval.
- [ ] Before/During/After values load where evidence exists.
- [ ] `Show all metrics` expands the compact metric set.
- [ ] Full telemetry remains available independently.
- [ ] UI wording does not present temporal correlation or Probable Domain as proven root cause.

## 10. Final source check and tag

After all validation is complete:

```bash
git status
git log -1 --oneline
./scripts/release-gate.sh
```

Only when the working tree is clean and the final gate passes should the RC commit
be tagged:

```bash
git tag -a v1.0.0-rc.1 -m "Wi-Fi Experience Monitor v1.0.0-rc.1"
git push origin v1.0.0-rc.1
```

The tag identifies a Release Candidate, not the final `v1.0.0` release.
