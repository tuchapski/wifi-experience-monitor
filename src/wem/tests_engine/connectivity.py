import re
import socket
import time
import urllib.error
import urllib.request

from wem.collectors.command import run_command
from wem.models.metrics import ConnectivityMetrics, TestOutcome
from wem.profiles.models import TestConfigurations


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
        request = urllib.request.Request(
            self.https_url,
            method="GET",
            headers={"User-Agent": "wifi-experience-monitor/0.1"},
        )

        failure_reason = "Test failed."
        started = time.perf_counter()

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.tests.https.timeout_seconds or 5.0,
            ) as response:
                elapsed = (time.perf_counter() - started) * 1000

                metrics.https_status_code = response.status

                metrics.https_success = 200 <= response.status < 400

                metrics.https_total_time_ms = round(
                    elapsed,
                    3,
                )

        except (
            urllib.error.URLError,
            TimeoutError,
        ) as exc:
            elapsed = (time.perf_counter() - started) * 1000

            metrics.https_success = False

            metrics.https_total_time_ms = round(
                elapsed,
                3,
            )

            failure_reason = f"HTTPS test failed: {exc}"
            if isinstance(exc, urllib.error.HTTPError):
                metrics.https_status_code = exc.code

        metrics.tests["https"] = TestOutcome(
            "passed" if metrics.https_success else "failed",
            f"HTTPS response: {metrics.https_status_code}."
            if metrics.https_success
            else failure_reason,
            "host",
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
    "https": ("https_success", "https_status_code", "https_total_time_ms"),
}
