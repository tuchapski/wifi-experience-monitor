from wifi_server.security import hash_agent_token, issue_agent_token


def test_agent_tokens_are_hashed_deterministically() -> None:
    assert hash_agent_token("secret") == hash_agent_token("secret")
    assert hash_agent_token("secret") != hash_agent_token("different")


def test_issued_agent_tokens_are_unique() -> None:
    assert issue_agent_token() != issue_agent_token()
