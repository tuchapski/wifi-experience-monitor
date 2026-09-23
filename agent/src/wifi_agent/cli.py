import argparse
import logging
import time
from datetime import UTC, datetime

import httpx

from wifi_agent.api import AgentApiClient
from wifi_agent.capabilities import discover_capabilities
from wifi_agent.config import AgentSettings
from wifi_agent.storage import AgentIdentity, AgentIdentityStore
from wifi_agent.system_info import collect_system_info

LOGGER = logging.getLogger("wifi_agent")


def _store(settings: AgentSettings) -> AgentIdentityStore:
    store = AgentIdentityStore(settings.data_dir / "agent.db")
    store.initialize()
    return store


def _enroll(
    settings: AgentSettings,
    store: AgentIdentityStore,
    force: bool = False,
) -> AgentIdentity:
    existing = store.load()
    if existing and not force:
        return existing

    capabilities = discover_capabilities()
    result = AgentApiClient(settings).enroll(collect_system_info(), capabilities)
    identity = AgentIdentity(
        agent_id=result.agent_id,
        agent_token=result.agent_token,
        server_url=settings.server_url,
        enrolled_at=result.enrolled_at,
    )
    store.save(identity)
    return identity


def _print_status(settings: AgentSettings, store: AgentIdentityStore) -> None:
    identity = store.load()
    capabilities = discover_capabilities()

    print(f"Agent name: {settings.name}")
    print(f"Agent type: {settings.agent_type}")
    print(f"Server: {settings.server_url}")
    print(f"Agent ID: {identity.agent_id if identity else 'not enrolled'}")
    print("Capabilities:")
    for capability in capabilities:
        print(f"  - {capability.name}")


def _heartbeat(settings: AgentSettings, identity: AgentIdentity) -> None:
    result = AgentApiClient(settings).heartbeat(identity)
    offset_ms = (result.server_time - datetime.now(UTC)).total_seconds() * 1000
    LOGGER.info(
        "heartbeat accepted agent_id=%s server_clock_offset_ms=%.1f commands=%d",
        identity.agent_id,
        offset_ms,
        len(result.commands),
    )


def _run(settings: AgentSettings, store: AgentIdentityStore) -> None:
    identity = _enroll(settings, store)
    if identity.server_url != settings.server_url:
        raise SystemExit(
            "Configured server does not match the server stored in the agent identity. "
            "Re-enroll with 'wifi-agent enroll --force'."
        )
    LOGGER.info("agent started agent_id=%s server=%s", identity.agent_id, settings.server_url)

    while True:
        try:
            _heartbeat(settings, identity)
        except (httpx.HTTPError, OSError) as exc:
            LOGGER.warning("heartbeat failed: %s", exc)
        time.sleep(settings.heartbeat_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(prog="wifi-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enroll_parser = subparsers.add_parser("enroll", help="Enroll this agent with the server")
    enroll_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("heartbeat", help="Send one heartbeat")
    subparsers.add_parser("run", help="Run the heartbeat loop")
    subparsers.add_parser("status", help="Show local agent identity and capabilities")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = AgentSettings.from_environment()
    store = _store(settings)

    if args.command == "enroll":
        identity = _enroll(settings, store, force=args.force)
        print(f"Enrolled agent: {identity.agent_id}")
        return

    if args.command == "status":
        _print_status(settings, store)
        return

    if args.command == "run":
        try:
            _run(settings, store)
        except KeyboardInterrupt:
            LOGGER.info("agent stopped")
        return

    identity = store.load()
    if identity is None:
        raise SystemExit("Agent is not enrolled. Run 'wifi-agent enroll' first.")
    if identity.server_url != settings.server_url:
        raise SystemExit(
            "Configured server does not match the server stored in the agent identity. "
            "Re-enroll with 'wifi-agent enroll --force'."
        )

    if args.command == "heartbeat":
        _heartbeat(settings, identity)
