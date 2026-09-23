from datetime import UTC, datetime, timedelta

from wifi_server.services.agents import is_agent_online


def test_agent_is_online_inside_heartbeat_window() -> None:
    now = datetime.now(UTC)
    assert is_agent_online(now - timedelta(seconds=5), now, 15)


def test_agent_is_offline_after_heartbeat_window() -> None:
    now = datetime.now(UTC)
    assert not is_agent_online(now - timedelta(seconds=16), now, 15)
