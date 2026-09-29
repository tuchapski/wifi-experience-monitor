# V1 Final Release Checklist

Target tag: `v1.0.0`

This checklist promotes the validated `v1.0.0-rc.1` line to the final V1 release.
No functional changes belong in this promotion commit.

## Release metadata

Active components must report:

```text
Server Python package   1.0.0
Agent Python package    1.0.0
Frontend package        1.0.0
FastAPI metadata        1.0.0
Git tag                 v1.0.0
```

The legacy root package remains on its historical version because it is not the
active V1 runtime.

## Local package update

```bash
cd ~/wifi-experience-monitor
source .venv/bin/activate
python -m pip install -e "server[dev]" -e "agent[dev]"
python -m pip show wifi-experience-server | grep Version
python -m pip show wifi-experience-agent | grep Version
```

Both packages must report `1.0.0`.

## Autonomous Agent update

Preserve the current identity and data:

```bash
sudo ./agent/install.sh   --server-url http://127.0.0.1:8000   --interface wlp0s20f3   --name sensor-local-01
```

Verify:

```bash
sudo /opt/wifi-experience-agent/venv/bin/python -m pip show   wifi-experience-agent | grep Version
systemctl is-enabled wifi-experience-agent
systemctl is-active wifi-experience-agent
```

Expected package version: `1.0.0`; service: `enabled` and `active`.

## Server smoke test

Restart `wifi-server`, then verify:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/openapi.json | jq -r '.info.version'
```

Expected:

```text
{"status":"ok"}
1.0.0
```

## Final quality gate

```bash
./scripts/release-gate.sh
git diff --check
```

All 11 checks must pass.

## Final commit and tag

After committing and pushing the promotion, require a clean tree and run the
gate once more on the exact commit to be tagged:

```bash
git status
git log -1 --oneline
./scripts/release-gate.sh
```

Then:

```bash
git tag -a v1.0.0 -m "Wi-Fi Experience Monitor v1.0.0"
git show --no-patch --decorate v1.0.0
git push origin v1.0.0
git ls-remote --tags origin | grep 'v1.0.0'
```

The `v1.0.0-rc.1` tag remains immutable as the tested release candidate.
