import re
import socket
import time

from wem.collectors.command import run_command
from wem.models.metrics import ApplicationTargetMetric, ConnectivityMetrics, TestOutcome
from wem.profiles.models import (
    ApplicationTargetConfig,
    TestConfigurations,
)
from wem.tests_engine.http_transaction import probe_http_transaction


class ConnectivityTester:
    def __init__(
        self,
        interface: str,
        gateway: str | None,
        dns_query: str = "example.com",
        internet_target: str = "1.1.1.1",
        https_url: str = "https://example.com",
        tests: TestConfigurations | None = None,
    ):
        self.interface = interface
        self.gateway = gateway
        self.tests = tests.model_copy(deep=True) if tests is not None else TestConfigurations()
        if tests is None:
            self.tests.dns.query = dns_query
            self.tests.internet.target = internet_target
            self.tests.https.url = https_url

        self.dns_query = self.tests.dns.query
        self.internet_target = self.tests.internet.target
        self.https_url = self.tests.https.url

        self.errors: list[str] = []

    def run(self) -> ConnectivityMetrics:
        metrics = ConnectivityMetrics()

        for name in ("gateway", "dns", "internet", "https"):
            config = getattr(self.tests, name)
            if config.enabled:
                partial = self.run_test(name)
                metrics.tests.update(partial.tests)
                for field_name in _TEST_FIELDS[name]:
                    setattr(metrics, field_name, getattr(partial, field_name))
            else:
                metrics.tests[name] = TestOutcome("disabled", "Test disabled by profile.")

        return metrics

    def run_test(self, name: str) -> ConnectivityMetrics:
        metrics = ConnectivityMetrics()
        runners = {
            "gateway": self._test_gateway,
            "dns": self._test_dns,
            "internet": self._test_internet,
            "https": self._test_https,
        }
        try:
            runner = runners[name]
        except KeyError as exc:
            raise ValueError(f"Unknown connectivity test: {name}") from exc
        runner(metrics)
        return metrics

    def _test_gateway(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        target = self.gateway if self.tests.gateway.automatic_gateway else self.tests.gateway.target
        if target is None:
            metrics.tests["gateway"] = TestOutcome("skipped", "No gateway was identified.")
            return

        (
            reachable,
            packet_loss,
            latency_min,
            latency_avg,
            latency_max,
            jitter,
        ) = self._ping(target, timeout=self.tests.gateway.timeout_seconds)

        metrics.gateway_reachable = reachable
        metrics.gateway_packet_loss_percent = packet_loss
        metrics.gateway_latency_min_ms = latency_min
        metrics.gateway_latency_avg_ms = latency_avg
        metrics.gateway_latency_max_ms = latency_max
        metrics.gateway_jitter_ms = jitter

        metrics.tests["gateway"] = self._ping_outcome(reachable, target)

    def _test_dns(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        metrics.dns_query = self.dns_query

        failure_reason = "Test failed."
        started = time.perf_counter()

        try:
            timeout = self.tests.dns.timeout_seconds
            if timeout is None:
                result = socket.getaddrinfo(
                    self.dns_query,
                    None,
                    family=socket.AF_INET,
                )
                address = str(result[0][4][0]) if result else None
            else:
                command_result = run_command(
                    ["getent", "ahostsv4", self.dns_query],
                    timeout=timeout,
                )
                if not command_result.success:
                    raise OSError(command_result.stderr or "No IPv4 address was returned.")
                first_line = command_result.stdout.splitlines()[0]
                address = first_line.split()[0] if first_line else None

            elapsed = (time.perf_counter() - started) * 1000

            metrics.dns_success = address is not None
            metrics.dns_latency_ms = round(
                elapsed,
                3,
            )

            metrics.dns_result = address

        except (OSError, IndexError) as exc:
            elapsed = (time.perf_counter() - started) * 1000

            metrics.dns_success = False
            metrics.dns_latency_ms = round(
                elapsed,
                3,
            )

            failure_reason = f"DNS resolution failed: {exc}"

        metrics.tests["dns"] = TestOutcome(
            "passed" if metrics.dns_success else "failed",
            "System resolver returned an address." if metrics.dns_success else failure_reason,
            "host",
        )

    def _test_internet(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        (
            reachable,
            packet_loss,
            latency_min,
            latency_avg,
            latency_max,
            jitter,
        ) = self._ping(
            self.internet_target,
            timeout=self.tests.internet.timeout_seconds,
        )

        metrics.internet_reachable = reachable
        metrics.internet_packet_loss_percent = packet_loss
        metrics.internet_latency_min_ms = latency_min
        metrics.internet_latency_avg_ms = latency_avg
        metrics.internet_latency_max_ms = latency_max
        metrics.internet_jitter_ms = jitter

        metrics.tests["internet"] = self._ping_outcome(reachable, self.internet_target)

    def _test_https(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        result = probe_http_transaction(
            self.https_url,
            self.tests.https.timeout_seconds or 5.0,
        )
        metrics.https_status_code = result.status_code
        metrics.https_dns_ms = result.dns_ms
        metrics.https_tcp_connect_ms = result.tcp_connect_ms
        metrics.https_tls_handshake_ms = result.tls_handshake_ms
        metrics.https_ttfb_ms = result.ttfb_ms
        metrics.https_total_time_ms = result.total_ms
        metrics.https_success = (
            result.status == "passed" if result.status in {"passed", "failed"} else None
        )
        if result.status == "error":
            self.errors.append(f"HTTPS collection failed: {result.reason}")

        metrics.tests["https"] = TestOutcome(
            result.status,
            result.reason,
            "host",
        )

    def run_application_target(self, config: ApplicationTargetConfig) -> ApplicationTargetMetric:
        try:
            if config.kind == "http":
                return self._test_application_http(config)
            if config.kind == "tcp":
                return self._test_application_tcp(config)
            return self._test_application_dns(config)
        except Exception as exc:
            self.errors.append(f"application target collection failed for {config.name}: {exc}")
            return self._target_metric(
                config,
                status="error",
                reason=f"Application target collection error: {exc}",
                latency_ms=None,
            )

    @staticmethod
    def _target_metric(
        config: ApplicationTargetConfig,
        *,
        status: str,
        reason: str,
        latency_ms: float | None,
        status_code: int | None = None,
        dns_ms: float | None = None,
        tcp_connect_ms: float | None = None,
        tls_handshake_ms: float | None = None,
        ttfb_ms: float | None = None,
    ) -> ApplicationTargetMetric:
        return ApplicationTargetMetric(
            name=config.name,
            kind=config.kind,
            target=config.target,
            port=config.port,
            status=status,
            reason=reason,
            latency_ms=latency_ms,
            status_code=status_code,
            dns_ms=dns_ms,
            tcp_connect_ms=tcp_connect_ms,
            tls_handshake_ms=tls_handshake_ms,
            ttfb_ms=ttfb_ms,
        )

    def _test_application_http(self, config: ApplicationTargetConfig) -> ApplicationTargetMetric:
        result = probe_http_transaction(
            config.target,
            config.timeout_seconds or 5.0,
        )
        if result.status == "error":
            self.errors.append(
                f"application target collection failed for {config.name}: {result.reason}"
            )
        return self._target_metric(
            config,
            status=result.status,
            reason=result.reason,
            latency_ms=result.total_ms,
            status_code=result.status_code,
            dns_ms=result.dns_ms,
            tcp_connect_ms=result.tcp_connect_ms,
            tls_handshake_ms=result.tls_handshake_ms,
            ttfb_ms=result.ttfb_ms,
        )

    def _test_application_tcp(self, config: ApplicationTargetConfig) -> ApplicationTargetMetric:
        assert config.port is not None
        started = time.perf_counter()
        try:
            with socket.create_connection(
                (config.target, config.port),
                timeout=config.timeout_seconds or 5.0,
            ):
                pass
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            return self._target_metric(
                config,
                status="passed",
                reason=f"TCP connection to {config.target}:{config.port} succeeded.",
                latency_ms=elapsed,
            )
        except (OSError, TimeoutError) as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            return self._target_metric(
                config,
                status="failed",
                reason=f"TCP connection failed: {exc}",
                latency_ms=elapsed,
            )

    def _test_application_dns(self, config: ApplicationTargetConfig) -> ApplicationTargetMetric:
        started = time.perf_counter()
        try:
            timeout = config.timeout_seconds
            if timeout is None:
                result = socket.getaddrinfo(config.target, None, family=socket.AF_INET)
                address = str(result[0][4][0]) if result else None
            else:
                command_result = run_command(["getent", "ahostsv4", config.target], timeout=timeout)
                if not command_result.success:
                    raise OSError(command_result.stderr or "No IPv4 address was returned.")
                first_line = command_result.stdout.splitlines()[0]
                address = first_line.split()[0] if first_line else None
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            if address is None:
                raise OSError("No IPv4 address was returned.")
            return self._target_metric(
                config,
                status="passed",
                reason=f"System resolver returned {address}.",
                latency_ms=elapsed,
            )
        except (OSError, IndexError) as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            return self._target_metric(
                config,
                status="failed",
                reason=f"DNS target failed: {exc}",
                latency_ms=elapsed,
            )

    def _ping_outcome(self, reachable: bool | None, target: str) -> TestOutcome:
        if reachable is None:
            return TestOutcome("error", getattr(self, "_ping_error", "Ping collection failed."))
        return TestOutcome(
            "passed" if reachable else "failed",
            f"ICMP replies received from {target}."
            if reachable
            else f"No ICMP replies from {target}; this alone does not prove a network outage.",
        )

    def _ping(
        self,
        target: str,
        timeout: float | None = None,
    ) -> tuple[
        bool | None,
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
    ]:
        result = run_command(
            [
                "ping",
                "-I",
                self.interface,
                "-c",
                "4",
                "-i",
                "0.2",
                "-W",
                "2",
                target,
            ],
            timeout=timeout or 6.0,
        )

        output = result.stdout

        loss_match = re.search(
            r"([\d.]+)% packet loss",
            output,
        )

        packet_loss = float(loss_match.group(1)) if loss_match else None

        latency_match = re.search(
            r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms",
            output,
        )

        latency_min = None
        latency_avg = None
        latency_max = None
        jitter = None

        if latency_match:
            latency_min = float(latency_match.group(1))

            latency_avg = float(latency_match.group(2))

            latency_max = float(latency_match.group(3))

            jitter = float(latency_match.group(4))

        if packet_loss is None or result.returncode not in {0, 1}:
            self._ping_error = result.stderr or "No valid ping statistics were returned."
            self.errors.append(f"ping collection failed for {target}: {self._ping_error}")
            return (None, None, None, None, None, None)
        reachable = packet_loss < 100.0

        return (
            reachable,
            packet_loss,
            latency_min,
            latency_avg,
            latency_max,
            jitter,
        )


_TEST_FIELDS = {
    "gateway": (
        "gateway_reachable",
        "gateway_packet_loss_percent",
        "gateway_latency_min_ms",
        "gateway_latency_avg_ms",
        "gateway_latency_max_ms",
        "gateway_jitter_ms",
    ),
    "dns": ("dns_success", "dns_latency_ms", "dns_query", "dns_result"),
    "internet": (
        "internet_reachable",
        "internet_packet_loss_percent",
        "internet_latency_min_ms",
        "internet_latency_avg_ms",
        "internet_latency_max_ms",
        "internet_jitter_ms",
    ),
    "https": (
        "https_success",
        "https_status_code",
        "https_dns_ms",
        "https_tcp_connect_ms",
        "https_tls_handshake_ms",
        "https_ttfb_ms",
        "https_total_time_ms",
    ),
}
