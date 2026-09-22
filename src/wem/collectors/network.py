import ipaddress
import re

from wem.collectors.command import run_command
from wem.models.metrics import NetworkMetrics


class NetworkCollector:
    def __init__(self, interface: str):
        self.interface = interface
        self.errors: list[str] = []

    def collect(self) -> NetworkMetrics:
        metrics = NetworkMetrics(interface=self.interface)

        self._collect_ipv4(metrics)
        self._collect_default_route(metrics)
        self._collect_dns(metrics)

        return metrics

    def _collect_ipv4(
        self,
        metrics: NetworkMetrics,
    ) -> None:
        result = run_command(
            [
                "ip",
                "-4",
                "-o",
                "addr",
                "show",
                "dev",
                self.interface,
                "scope",
                "global",
            ]
        )

        if not result.success:
            self.errors.append(f"ipv4 address collection failed: {result.stderr}")
            return

        match = re.search(
            r"\binet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)",
            result.stdout,
        )

        if not match:
            self.errors.append(f"no IPv4 address found on {self.interface}")
            return

        address = match.group(1)
        prefix_length = int(match.group(2))

        try:
            ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError:
            self.errors.append(f"invalid IPv4 address reported on {self.interface}: {address}")
            return

        metrics.ipv4_address = address
        metrics.prefix_length = prefix_length

    def _collect_default_route(
        self,
        metrics: NetworkMetrics,
    ) -> None:
        result = run_command(
            [
                "ip",
                "-4",
                "route",
                "show",
                "default",
                "dev",
                self.interface,
            ]
        )

        if not result.success:
            self.errors.append(f"default route collection failed: {result.stderr}")
            return

        match = re.search(
            r"\bdefault\s+via\s+(\d+\.\d+\.\d+\.\d+)",
            result.stdout,
        )

        if not match:
            self.errors.append(f"no default gateway found on {self.interface}")
            return

        gateway = match.group(1)

        try:
            ipaddress.IPv4Address(gateway)
        except ipaddress.AddressValueError:
            self.errors.append(f"invalid default gateway reported on {self.interface}: {gateway}")
            return

        metrics.gateway = gateway
        metrics.default_route_present = True

    def _collect_dns(
        self,
        metrics: NetworkMetrics,
    ) -> None:
        result = run_command(
            [
                "nmcli",
                "-t",
                "-f",
                "IP4.DNS",
                "device",
                "show",
                self.interface,
            ]
        )

        if not result.success:
            self.errors.append(f"dns collection failed: {result.stderr}")
            return

        dns_servers: list[str] = []

        for line in result.stdout.splitlines():
            line = line.strip()

            if not line:
                continue

            if ":" not in line:
                continue

            _, value = line.split(":", maxsplit=1)

            value = value.strip()

            if not value:
                continue

            try:
                ipaddress.IPv4Address(value)
            except ipaddress.AddressValueError:
                continue

            if value not in dns_servers:
                dns_servers.append(value)

        metrics.dns_servers = dns_servers

        if not dns_servers:
            self.errors.append(f"no IPv4 DNS servers found on {self.interface}")
