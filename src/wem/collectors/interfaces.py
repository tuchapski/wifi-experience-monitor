from dataclasses import asdict, dataclass

from wem.collectors.command import run_command


@dataclass(slots=True)
class WirelessInterface:
    name: str

    phy: str | None = None
    mac_address: str | None = None
    interface_type: str | None = None


class WirelessInterfaceDiscovery:
    def discover(
        self,
    ) -> list[WirelessInterface]:
        result = run_command(
            [
                "iw",
                "dev",
            ]
        )

        if not result.success:
            return []

        interfaces: list[WirelessInterface] = []

        current_phy: str | None = None

        current_interface: WirelessInterface | None = None

        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()

            if line.startswith("phy#"):
                if current_interface is not None:
                    interfaces.append(current_interface)

                    current_interface = None

                current_phy = line

                continue

            if line.startswith("Interface "):
                if current_interface is not None:
                    interfaces.append(current_interface)

                _, name = line.split(maxsplit=1)

                current_interface = WirelessInterface(
                    name=name,
                    phy=current_phy,
                )

                continue

            if current_interface is None:
                continue

            if line.startswith("addr "):
                _, address = line.split(maxsplit=1)

                current_interface.mac_address = address

            elif line.startswith("type "):
                _, interface_type = line.split(maxsplit=1)

                current_interface.interface_type = interface_type

        if current_interface is not None:
            interfaces.append(current_interface)

        return interfaces

    def discover_dicts(
        self,
    ) -> list[dict[str, str | None]]:
        return [asdict(interface) for interface in self.discover()]
