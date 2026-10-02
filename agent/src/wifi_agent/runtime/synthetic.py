"""Non-blocking orchestration for synthetic network probes."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime

from wifi_agent.collectors.connectivity import ProbeResult, probe_dns, probe_https, probe_ping
from wifi_agent.core import Observation, ObservationKind


class SyntheticProbeRuntime:
    def __init__(
        self,
        interface: str,
        *,
        dns_query: str,
        internet_target: str,
        https_url: str,
        timeout_seconds: float,
    ):
        self.interface = interface
        self.dns_query = dns_query
        self.internet_target = internet_target
        self.https_url = https_url
        self.timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="wem-probe")
        self._pending: dict[str, Future[ProbeResult]] = {}
        self._targets = {"dns": dns_query, "internet": internet_target, "https": https_url}

    @property
    def running(self) -> bool:
        return bool(self._pending)

    def start(self, gateway: str | None, source_address: str | None = None) -> bool:
        submitted = False
        if "dns" not in self._pending:
            self._pending["dns"] = self._executor.submit(
                probe_dns,
                self.dns_query,
                self.interface,
                self.timeout_seconds,
            )
            submitted = True
        if "internet" not in self._pending:
            self._pending["internet"] = self._executor.submit(
                probe_ping,
                "internet",
                self.internet_target,
                self.interface,
                self.timeout_seconds,
            )
            submitted = True
        if "https" not in self._pending:
            self._pending["https"] = self._executor.submit(
                probe_https,
                self.https_url,
                self.interface,
                self.timeout_seconds,
                source_address,
            )
            submitted = True
        if gateway and "gateway" not in self._pending:
            self._targets["gateway"] = gateway
            self._pending["gateway"] = self._executor.submit(
                probe_ping,
                "gateway",
                gateway,
                self.interface,
                self.timeout_seconds,
            )
            submitted = True
        return submitted

    def poll(self) -> ProbeResult | None:
        completed = [(name, future) for name, future in self._pending.items() if future.done()]
        if not completed:
            return None
        observations = []
        errors = []
        for name, future in completed:
            self._pending.pop(name, None)
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - defensive boundary around worker threads
                result = ProbeResult([], [f"synthetic {name} probe failed: {exc}"])
            observations.extend(result.observations)
            errors.extend(result.errors)
            if not result.observations and not result.errors:
                continue
            # An explicit error observation replaces any previously successful cached result.
            # Cache timestamps remain the probe's own completion time, never the Wi-Fi cycle time.
            observations.append(
                Observation(
                    source="synthetic",
                    kind=ObservationKind.STATE,
                    metric=f"network.{name}_collection_error",
                    value="; ".join(result.errors) or None,
                    observed_at=max(
                        (item.observed_at for item in result.observations),
                        default=datetime.now(UTC),
                    ),
                    labels={"interface": self.interface, "target": self._targets.get(name, "")},
                )
            )
        return ProbeResult(observations, errors)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
