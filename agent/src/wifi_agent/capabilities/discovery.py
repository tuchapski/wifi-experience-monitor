import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


def _wireless_interfaces() -> list[str]:
    sys_class_net = Path("/sys/class/net")
    if not sys_class_net.exists():
        return []

    return sorted(
        interface.name for interface in sys_class_net.iterdir() if (interface / "wireless").exists()
    )


def discover_capabilities() -> list[Capability]:
    """Discover capabilities supported by the local runtime and installed tools."""

    capabilities: list[Capability] = []
    interfaces = _wireless_interfaces()
    iw_path = shutil.which("iw")

    if iw_path:
        wifi_metadata = {"tool": iw_path, "interfaces": interfaces}
        for name in (
            "wifi.connection",
            "wifi.station_stats",
            "wifi.rf",
            "wifi.scan",
        ):
            capabilities.append(Capability(name=name, metadata=wifi_metadata))

    ping_path = shutil.which("ping")
    if ping_path:
        capabilities.append(Capability(name="network.icmp", metadata={"tool": ping_path}))

    capabilities.extend(
        [
            Capability(name="network.dns", metadata={"implementation": "python"}),
            Capability(name="network.http", metadata={"implementation": "httpx"}),
        ]
    )

    if platform.system() == "Linux":
        capabilities.extend(
            [
                Capability(name="system.cpu", metadata={"source": "/proc"}),
                Capability(name="system.memory", metadata={"source": "/proc"}),
            ]
        )

    tcpdump_path = shutil.which("tcpdump")
    if tcpdump_path:
        capabilities.append(Capability(name="capture.packet", metadata={"tool": tcpdump_path}))

    return sorted(capabilities, key=lambda capability: capability.name)
