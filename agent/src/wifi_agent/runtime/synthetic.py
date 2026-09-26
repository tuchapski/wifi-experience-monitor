"""Non-blocking orchestration for synthetic network probes."""

from concurrent.futures import Future, ThreadPoolExecutor

from wifi_agent.collectors.connectivity import ProbeResult, probe_dns, probe_https, probe_ping


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
                errors.append(f"synthetic {name} probe failed: {exc}")
                continue
            observations.extend(result.observations)
            errors.extend(result.errors)
        return ProbeResult(observations, errors)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
