from typing import Any

import httpx

from wifi_agent.config import AgentSettings
from wifi_agent.recording.models import LocalRecording, PendingRecordingBatch
from wifi_agent.storage import AgentIdentity


class RecordingApiClient:
    def __init__(self, settings: AgentSettings):
        self.settings = settings

    def acknowledge_command(
        self,
        identity: AgentIdentity,
        command_id: str,
        status: str,
        data: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        response = httpx.post(
            f"{self.settings.server_url}/api/v1/commands/{command_id}/ack",
            headers={"Authorization": f"Bearer {identity.agent_token}"},
            json={"status": status, "data": data or {}, "message": message},
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()

    def publish_batch(
        self,
        identity: AgentIdentity,
        batch: PendingRecordingBatch,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.settings.server_url}/api/v1/recordings/{batch.recording_id}/batches",
            headers={"Authorization": f"Bearer {identity.agent_token}"},
            json=batch.to_payload(),
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def publish_manifest(
        self,
        identity: AgentIdentity,
        recording: LocalRecording,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.settings.server_url}/api/v1/recordings/{recording.recording_id}/manifest",
            headers={"Authorization": f"Bearer {identity.agent_token}"},
            json=recording.manifest_payload(),
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
