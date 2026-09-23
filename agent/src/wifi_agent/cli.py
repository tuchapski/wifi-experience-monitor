import argparse
import logging
import time
from datetime import UTC, datetime

import httpx

from wifi_agent.api import AgentApiClient
from wifi_agent.capabilities import discover_capabilities
from wifi_agent.collectors import resolve_interface
from wifi_agent.config import AgentSettings
from wifi_agent.runtime import CurrentStateRuntime
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


def _selected_interface(settings: AgentSettings) -> str | None:
    return resolve_interface(settings.interface)


def _print_status(settings: AgentSettings, store: AgentIdentityStore) -> None:
    identity = store.load()
    capabilities = discover_capabilities()
    interface = _selected_interface(settings)

    print(f"Agent name: {settings.name}")
    print(f"Agent type: {settings.agent_type}")
    print(f"Server: {settings.server_url}")
    print(f"Agent ID: {identity.agent_id if identity else 'not enrolled'}")
    print(f"Wi-Fi interface: {interface or 'not detected'}")
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


def _publish_state(
    settings: AgentSettings,
    identity: AgentIdentity,
    runtime: CurrentStateRuntime,
) -> None:
    snapshot = runtime.collect()
    AgentApiClient(settings).publish_state(identity, snapshot)
    LOGGER.info(
        "current state published agent_id=%s interface=%s ssid=%s rssi=%s errors=%d",
        identity.agent_id,
        runtime.interface,
        snapshot.wifi.get("ssid"),
        snapshot.wifi.get("rssi_dbm"),
        len(snapshot.collector_errors),
    )


def _run(settings: AgentSettings, store: AgentIdentityStore) -> None:
    identity = _enroll(settings, store)
    if identity.server_url != settings.server_url:
        raise SystemExit(
            "Configured server does not match the server stored in the agent identity. "
            "Re-enroll with 'wifi-agent enroll --force'."
        )

    interface = _selected_interface(settings)
    runtime = CurrentStateRuntime(interface) if interface else None
    if runtime is None:
        LOGGER.warning("no wireless interface detected; current-state publication is disabled")

    LOGGER.info("agent started agent_id=%s server=%s", identity.agent_id, settings.server_url)
    next_heartbeat = 0.0
    next_state = 0.0

    while True:
        now = time.monotonic()
        if now >= next_heartbeat:
            try:
                _heartbeat(settings, identity)
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning("heartbeat failed: %s", exc)
            next_heartbeat = now + settings.heartbeat_interval_seconds

        if runtime is not None and now >= next_state:
            try:
                _publish_state(settings, identity, runtime)
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning("current-state publication failed: %s", exc)
            next_state = now + settings.state_interval_seconds

        next_due = min(next_heartbeat, next_state if runtime is not None else next_heartbeat)
        time.sleep(max(0.1, min(1.0, next_due - time.monotonic())))


def _validated_identity(settings: AgentSettings, store: AgentIdentityStore) -> AgentIdentity:
    identity = store.load()
    if identity is None:
        raise SystemExit("Agent is not enrolled. Run 'wifi-agent enroll' first.")
    if identity.server_url != settings.server_url:
        raise SystemExit(
            "Configured server does not match the server stored in the agent identity. "
            "Re-enroll with 'wifi-agent enroll --force'."
        )
    return identity


def main() -> None:
    parser = argparse.ArgumentParser(prog="wifi-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enroll_parser = subparsers.add_parser("enroll", help="Enroll this agent with the server")
    enroll_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("heartbeat", help="Send one heartbeat")
    subparsers.add_parser("state", help="Collect and publish one current-state snapshot")
    subparsers.add_parser("run", help="Run heartbeat and current-state loops")
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

    identity = _validated_identity(settings, store)
    if args.command == "heartbeat":
        _heartbeat(settings, identity)
        return

    if args.command == "state":
        interface = _selected_interface(settings)
        if interface is None:
            raise SystemExit("No wireless interface detected. Set WEM_AGENT_INTERFACE explicitly.")
        _publish_state(settings, identity, CurrentStateRuntime(interface))
