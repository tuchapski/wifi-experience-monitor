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

        (
            reachable,
            packet_loss,
            latency_min,
            latency_avg,
            latency_max,
            jitter,
        ) = self._ping(self.gateway)

        metrics.gateway_reachable = reachable
        metrics.gateway_packet_loss_percent = packet_loss
        metrics.gateway_latency_min_ms = latency_min
        metrics.gateway_latency_avg_ms = latency_avg
        metrics.gateway_latency_max_ms = latency_max
        metrics.gateway_jitter_ms = jitter

        if not reachable:
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
        (
            reachable,
            packet_loss,
            latency_min,
            latency_avg,
            latency_max,
            jitter,
        ) = self._ping(self.internet_target)

        metrics.internet_reachable = reachable
        metrics.internet_packet_loss_percent = packet_loss
        metrics.internet_latency_min_ms = latency_min
        metrics.internet_latency_avg_ms = latency_avg
        metrics.internet_latency_max_ms = latency_max
        metrics.internet_jitter_ms = jitter

        if not reachable:
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
    ) -> tuple[
        bool,
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
            timeout=6,
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

        reachable = result.success and packet_loss is not None and packet_loss < 100.0

        return (
            reachable,
            packet_loss,
            latency_min,
            latency_avg,
            latency_max,
            jitter,
        )
