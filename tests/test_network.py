from unittest.mock import patch

from wem.collectors.command import CommandResult
from wem.collectors.network import NetworkCollector

IP_ADDR_OUTPUT = """
3: wlp0s20f3    inet 192.168.15.13/24 brd 192.168.15.255 scope global dynamic wlp0s20f3
"""

IP_ROUTE_OUTPUT = """
default via 192.168.15.1 dev wlp0s20f3 proto dhcp src 192.168.15.13 metric 600
"""

DNS_OUTPUT = """
IP4.DNS[1]:10.128.60.11
IP4.DNS[2]:10.200.1.37
"""


def fake_run_command(command: list[str], timeout: float = 5.0) -> CommandResult:
    del timeout

    if command == [
        "ip",
        "-4",
        "-o",
        "addr",
        "show",
        "dev",
        "wlp0s20f3",
        "scope",
        "global",
    ]:
        return CommandResult(
            stdout=IP_ADDR_OUTPUT,
            stderr="",
            returncode=0,
        )

    if command == [
        "ip",
        "-4",
        "route",
        "show",
        "default",
        "dev",
        "wlp0s20f3",
    ]:
        return CommandResult(
            stdout=IP_ROUTE_OUTPUT,
            stderr="",
            returncode=0,
        )

    if command == [
        "nmcli",
        "-t",
        "-f",
        "IP4.DNS",
        "device",
        "show",
        "wlp0s20f3",
    ]:
        return CommandResult(
            stdout=DNS_OUTPUT,
            stderr="",
            returncode=0,
        )

    return CommandResult(
        stdout="",
        stderr="unexpected command",
        returncode=1,
    )


@patch(
    "wem.collectors.network.run_command",
    side_effect=fake_run_command,
)
def test_network_collector_parses_expected_network(mock_run_command) -> None:
    collector = NetworkCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.interface == "wlp0s20f3"

    assert metrics.ipv4_address == "192.168.15.13"
    assert metrics.prefix_length == 24

    assert metrics.gateway == "192.168.15.1"
    assert metrics.default_route_present is True

    assert metrics.dns_servers == [
        "10.128.60.11",
        "10.200.1.37",
    ]

    assert collector.errors == []

    assert mock_run_command.call_count == 3


@patch("wem.collectors.network.run_command")
def test_network_collector_handles_missing_ipv4(mock_run_command) -> None:
    def side_effect(command: list[str], timeout: float = 5.0) -> CommandResult:
        del timeout

        if command[:3] == ["ip", "-4", "-o"]:
            return CommandResult(
                stdout="",
                stderr="",
                returncode=0,
            )

        if command[:4] == ["ip", "-4", "route", "show"]:
            return CommandResult(
                stdout=IP_ROUTE_OUTPUT,
                stderr="",
                returncode=0,
            )

        return CommandResult(
            stdout=DNS_OUTPUT,
            stderr="",
            returncode=0,
        )

    mock_run_command.side_effect = side_effect

    collector = NetworkCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.ipv4_address is None
    assert metrics.prefix_length is None

    assert "no IPv4 address found on wlp0s20f3" in collector.errors


@patch("wem.collectors.network.run_command")
def test_network_collector_handles_missing_gateway(mock_run_command) -> None:
    def side_effect(command: list[str], timeout: float = 5.0) -> CommandResult:
        del timeout

        if command[:3] == ["ip", "-4", "-o"]:
            return CommandResult(
                stdout=IP_ADDR_OUTPUT,
                stderr="",
                returncode=0,
            )

        if command[:4] == ["ip", "-4", "route", "show"]:
            return CommandResult(
                stdout="",
                stderr="",
                returncode=0,
            )

        return CommandResult(
            stdout=DNS_OUTPUT,
            stderr="",
            returncode=0,
        )

    mock_run_command.side_effect = side_effect

    collector = NetworkCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.gateway is None
    assert metrics.default_route_present is False

    assert "no default gateway found on wlp0s20f3" in collector.errors


@patch("wem.collectors.network.run_command")
def test_network_collector_handles_missing_dns(mock_run_command) -> None:
    def side_effect(command: list[str], timeout: float = 5.0) -> CommandResult:
        del timeout

        if command[:3] == ["ip", "-4", "-o"]:
            return CommandResult(
                stdout=IP_ADDR_OUTPUT,
                stderr="",
                returncode=0,
            )

        if command[:4] == ["ip", "-4", "route", "show"]:
            return CommandResult(
                stdout=IP_ROUTE_OUTPUT,
                stderr="",
                returncode=0,
            )

        return CommandResult(
            stdout="",
            stderr="",
            returncode=0,
        )

    mock_run_command.side_effect = side_effect

    collector = NetworkCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.dns_servers == []

    assert "no IPv4 DNS servers found on wlp0s20f3" in collector.errors


@patch("wem.collectors.network.run_command")
def test_network_collector_handles_command_failures(mock_run_command) -> None:
    mock_run_command.return_value = CommandResult(
        stdout="",
        stderr="command failed",
        returncode=1,
    )

    collector = NetworkCollector("wlp0s20f3")

    metrics = collector.collect()

    assert metrics.ipv4_address is None
    assert metrics.gateway is None
    assert metrics.dns_servers == []
    assert metrics.default_route_present is False

    assert collector.errors == [
        "ipv4 address collection failed: command failed",
        "default route collection failed: command failed",
        "dns collection failed: command failed",
    ]
