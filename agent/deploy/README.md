# Autonomous Agent deployment

The V1 Agent can run as a persistent `systemd` service instead of depending on
an interactive terminal.

## Runtime layout

- executable environment: `/opt/wifi-experience-agent/venv`
- service configuration: `/etc/wifi-experience-agent/agent.env`
- persistent identity/spool/recording state: `/var/lib/wifi-experience-agent`
- service: `wifi-experience-agent.service`

The service runs as the dedicated `wifi-experience-agent` system user. It is not
run as root. The unit grants only `CAP_NET_ADMIN` and `CAP_NET_RAW`, which allow
the collector to access nl80211 survey information and ICMP probes while keeping
the rest of the process privileges bounded.

## First installation

Keep the Server running and stop any manually launched `wifi-agent run` process.
Then install the service:

```bash
sudo ./agent/install.sh \
  --server-url http://127.0.0.1:8000 \
  --interface wlp0s20f3 \
  --enrollment-token wifi-dev-enrollment \
  --name sensor-local-01
```

On first start the existing Agent runtime enrolls automatically and persists its
identity in `/var/lib/wifi-experience-agent/agent.db`.

## Preserve an existing development Agent identity

If the Agent was previously running with `WEM_AGENT_DATA_DIR=./data/agent`, stop
that process before copying the SQLite state and use:

```bash
sudo ./agent/install.sh \
  --server-url http://127.0.0.1:8000 \
  --interface wlp0s20f3 \
  --enrollment-token wifi-dev-enrollment \
  --name sensor-local-01 \
  --import-data-dir ./data/agent
```

Importing the data directory preserves the existing `agent.db`, including the
Agent ID/token, telemetry spool and recording state. The configured Server URL
must still match the Server URL stored in the imported identity.

## Operations

```bash
sudo systemctl status wifi-experience-agent
sudo journalctl -u wifi-experience-agent -f
sudo systemctl restart wifi-experience-agent
sudo systemctl stop wifi-experience-agent
sudo systemctl start wifi-experience-agent
```

The service is enabled for `multi-user.target`, waits for `network-online.target`
and restarts on process failure. If the Server is unavailable during a fresh
enrollment, `systemd` retries the Agent process; after enrollment, heartbeat,
state and telemetry synchronization already tolerate temporary Server/network
failures in the Agent runtime.
