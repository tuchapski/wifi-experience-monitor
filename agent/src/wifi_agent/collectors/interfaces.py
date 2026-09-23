from pathlib import Path


def discover_wireless_interfaces(sys_class_net: Path = Path("/sys/class/net")) -> list[str]:
    if not sys_class_net.exists():
        return []
    return sorted(
        interface.name for interface in sys_class_net.iterdir() if (interface / "wireless").exists()
    )


def resolve_interface(configured_interface: str | None) -> str | None:
    if configured_interface:
        return configured_interface
    interfaces = discover_wireless_interfaces()
    return interfaces[0] if interfaces else None
