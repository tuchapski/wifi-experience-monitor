import os
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentSettings:
    server_url: str
    enrollment_token: str | None
    data_dir: Path
    name: str
    agent_type: str
    heartbeat_interval_seconds: float
    state_interval_seconds: float
    telemetry_sample_interval_seconds: float
    telemetry_window_seconds: float
    telemetry_sync_interval_seconds: float
    telemetry_retention_hours: int
    request_timeout_seconds: float
    interface: str | None
    synthetic_probe_interval_seconds: float = 5.0
    synthetic_probe_timeout_seconds: float = 6.0
    dns_probe_query: str = "example.com"
    internet_probe_target: str = "1.1.1.1"
    https_probe_url: str = "https://example.com"

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        server_url = os.getenv("WEM_AGENT_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
        enrollment_token = os.getenv("WEM_AGENT_ENROLLMENT_TOKEN")
        data_dir = Path(os.getenv("WEM_AGENT_DATA_DIR", "./data/agent")).expanduser()
        name = os.getenv("WEM_AGENT_NAME", socket.gethostname())
        agent_type = os.getenv("WEM_AGENT_TYPE", "sensor")
        heartbeat_interval = float(os.getenv("WEM_AGENT_HEARTBEAT_INTERVAL_SECONDS", "5"))
        state_interval = float(os.getenv("WEM_AGENT_STATE_INTERVAL_SECONDS", "5"))
        telemetry_sample_interval = float(
            os.getenv("WEM_AGENT_TELEMETRY_SAMPLE_INTERVAL_SECONDS", "1")
        )
        telemetry_window = float(os.getenv("WEM_AGENT_TELEMETRY_WINDOW_SECONDS", "10"))
        telemetry_sync_interval = float(os.getenv("WEM_AGENT_TELEMETRY_SYNC_INTERVAL_SECONDS", "5"))
        telemetry_retention_hours = int(os.getenv("WEM_AGENT_TELEMETRY_RETENTION_HOURS", "24"))
        request_timeout = float(os.getenv("WEM_AGENT_REQUEST_TIMEOUT_SECONDS", "10"))
        interface = os.getenv("WEM_AGENT_INTERFACE") or None
        synthetic_probe_interval = float(
            os.getenv("WEM_AGENT_SYNTHETIC_PROBE_INTERVAL_SECONDS", "5")
        )
        synthetic_probe_timeout = float(os.getenv("WEM_AGENT_SYNTHETIC_PROBE_TIMEOUT_SECONDS", "6"))
        dns_probe_query = os.getenv("WEM_AGENT_DNS_PROBE_QUERY", "example.com").strip()
        internet_probe_target = os.getenv("WEM_AGENT_INTERNET_PROBE_TARGET", "1.1.1.1").strip()
        https_probe_url = os.getenv("WEM_AGENT_HTTPS_PROBE_URL", "https://example.com").strip()

        positive_values = {
            "WEM_AGENT_HEARTBEAT_INTERVAL_SECONDS": heartbeat_interval,
            "WEM_AGENT_STATE_INTERVAL_SECONDS": state_interval,
            "WEM_AGENT_TELEMETRY_SAMPLE_INTERVAL_SECONDS": telemetry_sample_interval,
            "WEM_AGENT_TELEMETRY_WINDOW_SECONDS": telemetry_window,
            "WEM_AGENT_TELEMETRY_SYNC_INTERVAL_SECONDS": telemetry_sync_interval,
            "WEM_AGENT_REQUEST_TIMEOUT_SECONDS": request_timeout,
            "WEM_AGENT_SYNTHETIC_PROBE_INTERVAL_SECONDS": synthetic_probe_interval,
            "WEM_AGENT_SYNTHETIC_PROBE_TIMEOUT_SECONDS": synthetic_probe_timeout,
        }
        for name_key, value in positive_values.items():
            if value <= 0:
                raise ValueError(f"{name_key} must be greater than zero")
        if telemetry_retention_hours <= 0:
            raise ValueError("WEM_AGENT_TELEMETRY_RETENTION_HOURS must be greater than zero")
        for name_key, value in {
            "WEM_AGENT_DNS_PROBE_QUERY": dns_probe_query,
            "WEM_AGENT_INTERNET_PROBE_TARGET": internet_probe_target,
            "WEM_AGENT_HTTPS_PROBE_URL": https_probe_url,
        }.items():
            if not value:
                raise ValueError(f"{name_key} must not be empty")

        return cls(
            server_url=server_url,
            enrollment_token=enrollment_token,
            data_dir=data_dir,
            name=name,
            agent_type=agent_type,
            heartbeat_interval_seconds=heartbeat_interval,
            state_interval_seconds=state_interval,
            telemetry_sample_interval_seconds=telemetry_sample_interval,
            telemetry_window_seconds=telemetry_window,
            telemetry_sync_interval_seconds=telemetry_sync_interval,
            telemetry_retention_hours=telemetry_retention_hours,
            request_timeout_seconds=request_timeout,
            interface=interface,
            synthetic_probe_interval_seconds=synthetic_probe_interval,
            synthetic_probe_timeout_seconds=synthetic_probe_timeout,
            dns_probe_query=dns_probe_query,
            internet_probe_target=internet_probe_target,
            https_probe_url=https_probe_url,
        )
