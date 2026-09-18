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
