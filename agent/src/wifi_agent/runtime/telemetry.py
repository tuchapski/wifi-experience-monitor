import logging

import httpx

from wifi_agent.api import AgentApiClient
from wifi_agent.config import AgentSettings
from wifi_agent.storage import AgentIdentity, TelemetrySpool

LOGGER = logging.getLogger("wifi_agent.telemetry")


class TelemetrySyncEngine:
    def __init__(
        self,
        settings: AgentSettings,
        identity: AgentIdentity,
        spool: TelemetrySpool,
    ):
        self.client = AgentApiClient(settings)
        self.identity = identity
        self.spool = spool

    def sync_pending(self, limit: int = 20) -> int:
        synced = 0

        for batch in self.spool.pending(limit=limit):
            try:
                result = self.client.publish_telemetry_batch(
                    self.identity,
                    batch,
                )
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning(
                    "telemetry sync failed batch_id=%s sequence=%d error=%s",
                    batch.batch_id,
                    batch.sequence,
                    exc,
                )
                break

            if not isinstance(result, dict):
                LOGGER.warning(
                    "telemetry batch returned invalid acknowledgement batch_id=%s response=%r",
                    batch.batch_id,
                    result,
                )
                break

            if result.get("status") not in {
                "accepted",
                "already_accepted",
            }:
                LOGGER.warning(
                    "telemetry batch was not acknowledged batch_id=%s response=%s",
                    batch.batch_id,
                    result,
                )
                break

            self.spool.acknowledge(batch.batch_id)
            synced += 1

        return synced
