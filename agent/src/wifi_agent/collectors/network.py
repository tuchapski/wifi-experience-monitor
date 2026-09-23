import ipaddress
import re
from datetime import UTC, datetime

from wifi_agent.collectors.command import run_command
from wifi_agent.core import Observation, ObservationKind


class NetworkStateCollector:
    def __init__(self, interface: str):
        self.interface = interface
        self.errors: list[str] = []

    def collect(self) -> list[Observation]:
        self.errors.clear()
        observed_at = datetime.now(UTC)
        values: dict[str, int | str] = {}

        address = run_command(
            ["ip", "-4", "-o", "addr", "show", "dev", self.interface, "scope", "global"]
        )
        if address.success:
            match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", address.stdout)
            if match:
                try:
                    ipaddress.IPv4Address(match.group(1))
                except ipaddress.AddressValueError:
                    self.errors.append("invalid IPv4 address reported by ip")
                else:
                    values["network.ipv4_address"] = match.group(1)
                    values["network.prefix_length"] = int(match.group(2))
            else:
                self.errors.append(f"no IPv4 address found on {self.interface}")
        else:
            self.errors.append(f"ipv4 address collection failed: {address.stderr}")

        route = run_command(["ip", "-4", "route", "show", "default", "dev", self.interface])
        if route.success:
            match = re.search(r"\bdefault\s+via\s+(\d+\.\d+\.\d+\.\d+)", route.stdout)
            if match:
                try:
                    ipaddress.IPv4Address(match.group(1))
                except ipaddress.AddressValueError:
                    self.errors.append("invalid default gateway reported by ip")
                else:
                    values["network.gateway"] = match.group(1)
            else:
                self.errors.append(f"no default gateway found on {self.interface}")
        else:
            self.errors.append(f"default route collection failed: {route.stderr}")

        return [
            Observation(
                source="network",
                kind=ObservationKind.STATE,
                metric=metric,
                value=value,
                observed_at=observed_at,
                labels={"interface": self.interface},
            )
            for metric, value in values.items()
        ]
