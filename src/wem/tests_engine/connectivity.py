import re
import socket
import time
import urllib.error
import urllib.request

from wem.collectors.command import run_command
from wem.models.metrics import ConnectivityMetrics


class ConnectivityTester:
    def __init__(
        self,
        interface: str,
        gateway: str | None,
        dns_query: str = "example.com",
        internet_target: str = "1.1.1.1",
        https_url: str = "https://example.com",
    ):
        self.interface = interface
        self.gateway = gateway
        self.dns_query = dns_query
        self.internet_target = internet_target
        self.https_url = https_url

        self.errors: list[str] = []

    def run(self) -> ConnectivityMetrics:
        metrics = ConnectivityMetrics()

        self._test_gateway(metrics)
        self._test_dns(metrics)
        self._test_internet(metrics)
        self._test_https(metrics)

        return metrics

    def _test_gateway(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        if self.gateway is None:
            self.errors.append("gateway test skipped: no gateway configured")
            return

        success, latency = self._ping(self.gateway)

        metrics.gateway_reachable = success
        metrics.gateway_latency_ms = latency

        if not success:
            self.errors.append(f"gateway unreachable: {self.gateway}")

    def _test_dns(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        metrics.dns_query = self.dns_query

        started = time.perf_counter()

        try:
            result = socket.getaddrinfo(
                self.dns_query,
                None,
                family=socket.AF_INET,
            )

            elapsed = (time.perf_counter() - started) * 1000

            metrics.dns_success = True
            metrics.dns_latency_ms = round(
                elapsed,
                3,
            )

            if result:
                metrics.dns_result = str(result[0][4][0])

        except OSError as exc:
            elapsed = (time.perf_counter() - started) * 1000

            metrics.dns_success = False
            metrics.dns_latency_ms = round(
                elapsed,
                3,
            )

            self.errors.append(f"dns resolution failed: {exc}")

    def _test_internet(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        success, latency = self._ping(self.internet_target)

        metrics.internet_reachable = success
        metrics.internet_latency_ms = latency

        if not success:
            self.errors.append(f"internet target unreachable: {self.internet_target}")

    def _test_https(
        self,
        metrics: ConnectivityMetrics,
    ) -> None:
        request = urllib.request.Request(
            self.https_url,
            method="GET",
            headers={"User-Agent": "wifi-experience-monitor/0.1"},
        )

        started = time.perf_counter()

        try:
            with urllib.request.urlopen(
                request,
                timeout=5,
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

            self.errors.append(f"https test failed: {exc}")

    def _ping(
        self,
        target: str,
    ) -> tuple[bool, float | None]:
        result = run_command(
            [
                "ping",
                "-I",
                self.interface,
                "-c",
                "1",
                "-W",
                "2",
                target,
            ],
            timeout=4,
        )

        if not result.success:
            return False, None

        match = re.search(
            r"time[=<]([\d.]+)\s*ms",
            result.stdout,
        )

        if not match:
            return True, None

        return True, float(match.group(1))
