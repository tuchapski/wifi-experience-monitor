"""Non-blocking scheduler and runtime readiness for Wi-Fi RF scans."""

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic

from wifi_agent.collectors.rf_scan import RfScanCollector
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.core.rf import RfScanResult
from wifi_agent.recording.context import get_active_recording_id


class RfScanRuntime:
    """Run active scans away from the high-frequency Current State loop."""

    def __init__(
        self,
        interface: str,
        *,
        interval_seconds: float = 60.0,
        timeout_seconds: float = 15.0,
    ):
        if interval_seconds <= 0:
            raise ValueError("RF scan interval must be greater than zero")
        if timeout_seconds <= 0:
            raise ValueError("RF scan timeout must be greater than zero")

        self.interface = interface
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.collector = RfScanCollector(interface, timeout_seconds=timeout_seconds)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wem-rf-scan")
        self._pending: Future[RfScanResult] | None = None
        self._pending_recording_id: str | None = None
        self._latest: RfScanResult | None = None
        self._next_scan_at = 0.0
        self._stale_after_seconds = max(interval_seconds * 3, timeout_seconds * 2)

    @property
    def running(self) -> bool:
        return self._pending is not None

    @property
    def latest_result(self) -> RfScanResult | None:
        return self._latest

    @property
    def next_scan_at(self) -> float:
        return self._next_scan_at

    def maybe_start(self, now: float | None = None) -> bool:
        """Start one scan when due, refusing overlapping scan attempts."""

        current = monotonic() if now is None else now
        if self._pending is not None or current < self._next_scan_at:
            return False

        self._pending_recording_id = get_active_recording_id()
        self._pending = self._executor.submit(self.collector.collect)
        self._next_scan_at = current + self.interval_seconds
        return True

    def poll(self) -> RfScanResult | None:
        """Return a newly completed scan, if any, and update runtime state."""

        future = self._pending
        if future is None or not future.done():
            return None

        self._pending = None
        recording_id = self._pending_recording_id
        self._pending_recording_id = None
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            result = RfScanResult(
                interface=self.interface,
                observed_at=datetime.now(UTC),
                duration_ms=0,
                error=f"rf scan worker failed: {exc}",
                recording_id=recording_id,
            )
        else:
            if recording_id is not None and result.recording_id is None:
                result = replace(result, recording_id=recording_id)
        self._latest = result
        return result

    def readiness_observations(
        self,
        now: datetime | None = None,
    ) -> list[Observation]:
        """Summarize scan runtime health without publishing the BSS inventory."""

        observed_at = now or datetime.now(UTC)
        latest = self._latest

        if latest is None:
            status = "pending"
            reason = (
                "Active Wi-Fi scan is running; no completed runtime verification exists yet."
                if self.running
                else "Active Wi-Fi scan has not completed yet."
            )
        elif not latest.success:
            status = "unavailable"
            reason = latest.error or "The latest active Wi-Fi scan failed."
        else:
            age_seconds = max(0.0, (observed_at - latest.observed_at).total_seconds())
            if age_seconds > self._stale_after_seconds:
                status = "degraded"
                reason = f"Last successful active Wi-Fi scan is stale ({age_seconds:.0f}s old)."
            else:
                status = "verified"
                reason = (
                    "Active Wi-Fi scan completed successfully and observed "
                    f"{len(latest.bsses)} BSS"
                    f"{'' if len(latest.bsses) == 1 else 's'}."
                )

        labels = {"interface": self.interface}
        observations = [
            Observation(
                source="wifi-scan-readiness",
                kind=ObservationKind.STATE,
                metric="wifi.scan_status",
                value=status,
                observed_at=observed_at,
                labels=labels,
            ),
            Observation(
                source="wifi-scan-readiness",
                kind=ObservationKind.STATE,
                metric="wifi.scan_reason",
                value=reason,
                observed_at=observed_at,
                labels=labels,
            ),
            Observation(
                source="wifi-scan-readiness",
                kind=ObservationKind.STATE,
                metric="wifi.scan_running",
                value=self.running,
                observed_at=observed_at,
                labels=labels,
            ),
        ]

        if latest is not None:
            observations.extend(
                [
                    Observation(
                        source="wifi-scan-readiness",
                        kind=ObservationKind.STATE,
                        metric="wifi.scan_last_completed_at",
                        value=latest.observed_at.isoformat(),
                        observed_at=observed_at,
                        labels=labels,
                    ),
                    Observation(
                        source="wifi-scan-readiness",
                        kind=ObservationKind.GAUGE,
                        metric="wifi.scan_duration_ms",
                        value=round(latest.duration_ms, 1),
                        unit="ms",
                        observed_at=observed_at,
                        labels=labels,
                    ),
                    Observation(
                        source="wifi-scan-readiness",
                        kind=ObservationKind.STATE,
                        metric="wifi.scan_bss_count",
                        value=len(latest.bsses),
                        observed_at=observed_at,
                        labels=labels,
                    ),
                    Observation(
                        source="wifi-scan-readiness",
                        kind=ObservationKind.STATE,
                        metric="wifi.scan_associated_seen",
                        value=latest.associated_bss is not None,
                        observed_at=observed_at,
                        labels=labels,
                    ),
                ]
            )

        return observations

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
