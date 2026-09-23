import argparse
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from wifi_agent.api import AgentApiClient, HeartbeatResult
from wifi_agent.capabilities import discover_capabilities
from wifi_agent.collectors import resolve_interface
from wifi_agent.config import AgentSettings
from wifi_agent.processors import CurrentStateSnapshot, TelemetryAggregator
from wifi_agent.recording import RecordingController
from wifi_agent.runtime import CurrentStateRuntime, TelemetrySyncEngine
from wifi_agent.storage import AgentIdentity, AgentIdentityStore, TelemetrySpool
from wifi_agent.system_info import collect_system_info

LOGGER = logging.getLogger("wifi_agent")


def _database_path(settings: AgentSettings) -> Path:
    return settings.data_dir / "agent.db"


def _store(settings: AgentSettings) -> AgentIdentityStore:
    store = AgentIdentityStore(_database_path(settings))
    store.initialize()
    return store


def _telemetry_spool(settings: AgentSettings) -> TelemetrySpool:
    spool = TelemetrySpool(_database_path(settings))
    spool.initialize()
    return spool


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


def _print_status(
    settings: AgentSettings,
    store: AgentIdentityStore,
    spool: TelemetrySpool,
) -> None:
    identity = store.load()
    capabilities = discover_capabilities()
    interface = _selected_interface(settings)

    print(f"Agent name: {settings.name}")
    print(f"Agent type: {settings.agent_type}")
    print(f"Server: {settings.server_url}")
    print(f"Agent ID: {identity.agent_id if identity else 'not enrolled'}")
    print(f"Wi-Fi interface: {interface or 'not detected'}")
    print(f"Pending telemetry batches: {spool.pending_count()}")
    print("Capabilities:")
    for capability in capabilities:
        print(f"  - {capability.name}")


def _heartbeat(
    settings: AgentSettings,
    identity: AgentIdentity,
    recording: dict[str, Any] | None = None,
) -> HeartbeatResult:
    result = AgentApiClient(settings).heartbeat(identity, recording=recording)
    offset_ms = (result.server_time - datetime.now(UTC)).total_seconds() * 1000
    LOGGER.info(
        "heartbeat accepted agent_id=%s server_clock_offset_ms=%.1f commands=%d",
        identity.agent_id,
        offset_ms,
        len(result.commands),
    )
    return result


def _publish_snapshot(
    settings: AgentSettings,
    identity: AgentIdentity,
    runtime: CurrentStateRuntime,
    snapshot: CurrentStateSnapshot,
) -> None:
    AgentApiClient(settings).publish_state(identity, snapshot)
    LOGGER.info(
        "current state published agent_id=%s interface=%s ssid=%s rssi=%s errors=%d",
        identity.agent_id,
        runtime.interface,
        snapshot.wifi.get("ssid"),
        snapshot.wifi.get("rssi_dbm"),
        len(snapshot.collector_errors),
    )


def _publish_state(
    settings: AgentSettings,
    identity: AgentIdentity,
    runtime: CurrentStateRuntime,
) -> None:
    _publish_snapshot(settings, identity, runtime, runtime.collect())


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
        LOGGER.warning(
            "no wireless interface detected; state and telemetry collection are disabled"
        )

    spool = _telemetry_spool(settings)
    cutoff = datetime.now(UTC) - timedelta(hours=settings.telemetry_retention_hours)
    pruned = spool.prune_before(cutoff)
    if pruned:
        LOGGER.info("pruned %d expired local telemetry batches", pruned)

    aggregator = TelemetryAggregator(settings.telemetry_window_seconds)
    sync_engine = TelemetrySyncEngine(settings, identity, spool)
    recording_controller = RecordingController(settings, identity, _database_path(settings))

    LOGGER.info("agent started agent_id=%s server=%s", identity.agent_id, settings.server_url)
    next_heartbeat = 0.0
    next_collection = 0.0
    next_state = 0.0
    next_sync = 0.0

    while True:
        now = time.monotonic()
        if now >= next_heartbeat:
            try:
                heartbeat = _heartbeat(
                    settings,
                    identity,
                    recording_controller.heartbeat_payload(),
                )
                recording_controller.handle_commands(heartbeat.commands)
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning("heartbeat failed: %s", exc)
            next_heartbeat = now + settings.heartbeat_interval_seconds

        if runtime is not None and now >= next_collection:
            cycle = runtime.collect_cycle()
            aggregator.consume(cycle.observations)
            recording_controller.consume(cycle.observations)

            if now >= next_state:
                try:
                    _publish_snapshot(settings, identity, runtime, cycle.snapshot)
                except (httpx.HTTPError, OSError) as exc:
                    LOGGER.warning("current-state publication failed: %s", exc)
                next_state = now + settings.state_interval_seconds

            points = aggregator.flush_if_due(cycle.snapshot.observed_at)
            batch = spool.enqueue(points, cycle.snapshot.observed_at)
            if batch is not None:
                LOGGER.info(
                    "telemetry batch queued batch_id=%s sequence=%d items=%d",
                    batch.batch_id,
                    batch.sequence,
                    len(batch.items),
                )
            next_collection = now + settings.telemetry_sample_interval_seconds

        if now >= next_sync:
            synced = sync_engine.sync_pending()
            if synced:
                LOGGER.info("telemetry batches synchronized count=%d", synced)
            recording_synced = recording_controller.sync_pending()
            if recording_synced:
                LOGGER.info("recording batches synchronized count=%d", recording_synced)
            next_sync = now + settings.telemetry_sync_interval_seconds

        due = [next_heartbeat, next_sync]
        if runtime is not None:
            due.extend([next_collection, next_state])
        time.sleep(max(0.1, min(1.0, min(due) - time.monotonic())))


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
    subparsers.add_parser("run", help="Run heartbeat, state and telemetry loops")
    subparsers.add_parser("status", help="Show local agent identity and capabilities")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = AgentSettings.from_environment()
    store = _store(settings)
    spool = _telemetry_spool(settings)

    if args.command == "enroll":
        identity = _enroll(settings, store, force=args.force)
        print(f"Enrolled agent: {identity.agent_id}")
        return

    if args.command == "status":
        _print_status(settings, store, spool)
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
