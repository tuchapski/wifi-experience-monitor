import logging

import httpx

from wifi_agent.api import AgentApiClient
from wifi_agent.config import AgentSettings
from wifi_agent.storage import AgentIdentity, RfScanSpool

LOGGER = logging.getLogger("wifi_agent.rf_sync")


class RfScanSyncEngine:
    def __init__(
        self,
        settings: AgentSettings,
        identity: AgentIdentity,
        spool: RfScanSpool,
    ):
        self.client = AgentApiClient(settings)
        self.identity = identity
        self.spool = spool

    def sync_pending(self, limit: int = 20) -> int:
        synced = 0
        for scan in self.spool.pending(limit=limit):
            try:
                result = self.client.publish_rf_scan(self.identity, scan)
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning(
                    "RF scan sync failed scan_id=%s sequence=%d error=%s",
                    scan.scan_id,
                    scan.sequence,
                    exc,
                )
                break

            if not isinstance(result, dict):
                LOGGER.warning(
                    "RF scan returned invalid acknowledgement scan_id=%s response=%r",
                    scan.scan_id,
                    result,
                )
                break

            if result.get("status") not in {"accepted", "already_accepted"}:
                LOGGER.warning(
                    "RF scan was not acknowledged scan_id=%s response=%s",
                    scan.scan_id,
                    result,
                )
                break

            self.spool.acknowledge(scan.scan_id)
            synced += 1
        return synced
