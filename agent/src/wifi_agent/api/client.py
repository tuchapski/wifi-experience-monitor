from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from wifi_agent import __version__
from wifi_agent.capabilities import Capability
from wifi_agent.config import AgentSettings
from wifi_agent.processors import CurrentStateSnapshot
from wifi_agent.storage import AgentIdentity
from wifi_agent.system_info import SystemInfo


@dataclass(frozen=True, slots=True)
class EnrollmentResult:
    agent_id: str
    agent_token: str
    config_revision: int
    enrolled_at: datetime


@dataclass(frozen=True, slots=True)
class HeartbeatResult:
    server_time: datetime
    desired_config_revision: int
    commands: list[dict[str, Any]]


class AgentApiClient:
    def __init__(self, settings: AgentSettings):
        self.settings = settings

    def enroll(
        self,
        system_info: SystemInfo,
        capabilities: list[Capability],
    ) -> EnrollmentResult:
        if not self.settings.enrollment_token:
            raise RuntimeError("WEM_AGENT_ENROLLMENT_TOKEN is required for enrollment")

        response = httpx.post(
            f"{self.settings.server_url}/api/v1/agents/enroll",
            json={
                "enrollment_token": self.settings.enrollment_token,
                "name": self.settings.name,
                "hostname": system_info.hostname,
                "agent_type": self.settings.agent_type,
                "agent_version": __version__,
                "os_name": system_info.os_name,
                "os_version": system_info.os_version,
                "capabilities": [
                    {
                        "capability": capability.name,
                        "enabled": capability.enabled,
                        "metadata": capability.metadata,
                    }
                    for capability in capabilities
                ],
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        return EnrollmentResult(
            agent_id=payload["agent_id"],
            agent_token=payload["agent_token"],
            config_revision=payload["config_revision"],
            enrolled_at=datetime.fromisoformat(payload["enrolled_at"]),
        )

    def heartbeat(self, identity: AgentIdentity) -> HeartbeatResult:
        response = httpx.post(
            f"{self.settings.server_url}/api/v1/agents/{identity.agent_id}/heartbeat",
            headers={"Authorization": f"Bearer {identity.agent_token}"},
            json={
                "timestamp": datetime.now(UTC).isoformat(),
                "agent_version": __version__,
                "config_revision": 0,
                "recording": {"active": False},
                "health": {
                    "collector": "ok",
                    "storage": "ok",
                    "sync": "ok",
                },
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        return HeartbeatResult(
            server_time=datetime.fromisoformat(payload["server_time"]),
            desired_config_revision=payload["desired_config_revision"],
            commands=payload["commands"],
        )

    def publish_state(
        self,
        identity: AgentIdentity,
        snapshot: CurrentStateSnapshot,
    ) -> dict[str, Any]:
        response = httpx.put(
            f"{self.settings.server_url}/api/v1/agents/{identity.agent_id}/state",
            headers={"Authorization": f"Bearer {identity.agent_token}"},
            json=snapshot.to_payload(),
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
