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
    request_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        server_url = os.getenv("WEM_AGENT_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
        enrollment_token = os.getenv("WEM_AGENT_ENROLLMENT_TOKEN")
        data_dir = Path(os.getenv("WEM_AGENT_DATA_DIR", "./data/agent")).expanduser()
        name = os.getenv("WEM_AGENT_NAME", socket.gethostname())
        agent_type = os.getenv("WEM_AGENT_TYPE", "sensor")
        heartbeat_interval = float(os.getenv("WEM_AGENT_HEARTBEAT_INTERVAL_SECONDS", "5"))
        request_timeout = float(os.getenv("WEM_AGENT_REQUEST_TIMEOUT_SECONDS", "10"))

        if heartbeat_interval <= 0:
            raise ValueError("WEM_AGENT_HEARTBEAT_INTERVAL_SECONDS must be greater than zero")
        if request_timeout <= 0:
            raise ValueError("WEM_AGENT_REQUEST_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            server_url=server_url,
            enrollment_token=enrollment_token,
            data_dir=data_dir,
            name=name,
            agent_type=agent_type,
            heartbeat_interval_seconds=heartbeat_interval,
            request_timeout_seconds=request_timeout,
        )
