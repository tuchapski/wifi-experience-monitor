from datetime import UTC, datetime

from wifi_agent.storage import AgentIdentity, AgentIdentityStore


def test_identity_store_round_trip(tmp_path) -> None:
    store = AgentIdentityStore(tmp_path / "agent.db")
    store.initialize()
    identity = AgentIdentity(
        agent_id="agt_123",
        agent_token="secret-token",
        server_url="http://127.0.0.1:8000",
        enrolled_at=datetime(2026, 9, 23, 20, 0, tzinfo=UTC),
    )

    store.save(identity)

    assert store.load() == identity


def test_identity_store_can_clear_identity(tmp_path) -> None:
    store = AgentIdentityStore(tmp_path / "agent.db")
    store.initialize()
    store.save(
        AgentIdentity(
            agent_id="agt_123",
            agent_token="secret-token",
            server_url="http://127.0.0.1:8000",
            enrolled_at=datetime.now(UTC),
        )
    )

    store.clear()

    assert store.load() is None
