from wifi_agent.capabilities import discovery


def test_capability_discovery_uses_available_linux_tools(monkeypatch) -> None:
    tools = {
        "iw": "/usr/sbin/iw",
        "ping": "/usr/bin/ping",
        "tcpdump": "/usr/bin/tcpdump",
    }
    monkeypatch.setattr(discovery.shutil, "which", lambda name: tools.get(name))
    monkeypatch.setattr(discovery.platform, "system", lambda: "Linux")
    monkeypatch.setattr(discovery, "_wireless_interfaces", lambda: ["wlp0s20f3"])

    capabilities = discovery.discover_capabilities()
    names = {capability.name for capability in capabilities}

    assert "wifi.station_stats" in names
    assert "network.icmp" in names
    assert "network.dns" in names
    assert "network.http" in names
    assert "capture.packet" in names
    assert "system.cpu" in names
