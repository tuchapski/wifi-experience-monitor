import platform
import socket
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemInfo:
    hostname: str
    os_name: str
    os_version: str


def collect_system_info() -> SystemInfo:
    os_name = platform.system()
    os_version = platform.release()

    if platform.system() == "Linux":
        try:
            os_release = platform.freedesktop_os_release()
        except OSError:
            os_release = {}
        os_name = os_release.get("NAME", os_name)
        os_version = os_release.get("VERSION_ID", os_version)

    return SystemInfo(
        hostname=socket.gethostname(),
        os_name=os_name,
        os_version=os_version,
    )
