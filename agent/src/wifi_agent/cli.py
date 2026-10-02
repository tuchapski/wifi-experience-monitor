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
from wifi_agent.core import Observation
from wifi_agent.processors import CurrentStateSnapshot, TelemetryAggregator
from wifi_agent.recording import RecordingController
from wifi_agent.runtime import (
    CurrentStateRuntime,
    RfScanRuntime,
    RfScanSyncEngine,
    TelemetrySyncEngine,
)
from wifi_agent.runtime.experience_profile import ExperienceProfileRuntime
from wifi_agent.storage import AgentIdentity, AgentIdentityStore, RfScanSpool, TelemetrySpool
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


def _rf_scan_spool(settings: AgentSettings) -> RfScanSpool:
    spool = RfScanSpool(_database_path(settings))
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
    rf_spool: RfScanSpool,
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
    print(f"Pending RF scans: {rf_spool.pending_count()}")
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


_PROBE_PREFIXES = (
    "network.gateway_",
    "network.dns_",
    "network.internet_",
    "network.https_",
)


def _update_probe_cache(
    cache: dict[str, Observation],
    observations: list[Observation],
) -> None:
    refreshed_prefixes = {
        prefix
        for observation in observations
        for prefix in _PROBE_PREFIXES
        if observation.metric.startswith(prefix)
    }
    for metric in list(cache):
        if any(metric.startswith(prefix) for prefix in refreshed_prefixes):
            cache.pop(metric)
    for observation in observations:
        cache[observation.metric] = observation


def _fresh_probe_observations(
    cache: dict[str, Observation],
    max_age_seconds: float,
    now: datetime | None = None,
) -> list[Observation]:
    now = now or datetime.now(UTC)
    return [
        observation
        for observation in cache.values()
        if 0 <= (now - observation.observed_at).total_seconds() <= max_age_seconds
    ]


def _service_rf_scan(
    runtime: RfScanRuntime,
    spool: RfScanSpool,
    now: float,
) -> None:
    completed = runtime.poll()
    if completed is not None:
        if completed.success:
            queued = spool.enqueue(completed)
            LOGGER.info(
                "RF scan completed interface=%s bsses=%d duration_ms=%.1f scan_id=%s sequence=%s",
                runtime.interface,
                len(completed.bsses),
                completed.duration_ms,
                queued.scan_id if queued else None,
                queued.sequence if queued else None,
            )
        else:
            LOGGER.warning("RF scan failed: %s", completed.error)
    runtime.maybe_start(now)


def _run(settings: AgentSettings, store: AgentIdentityStore) -> None:
    identity = _enroll(settings, store)
    if identity.server_url != settings.server_url:
        raise SystemExit(
            "Configured server does not match the server stored in the agent identity. "
            "Re-enroll with 'wifi-agent enroll --force'."
        )

    interface = _selected_interface(settings)
    runtime = (
        CurrentStateRuntime(interface, settings.telemetry_sample_interval_seconds)
        if interface
        else None
    )
    if runtime is None:
        LOGGER.warning(
            "no wireless interface detected; state and telemetry collection are disabled"
        )

    scan_runtime = (
        RfScanRuntime(
            interface,
            interval_seconds=settings.rf_scan_interval_seconds,
            timeout_seconds=settings.rf_scan_timeout_seconds,
        )
        if interface and settings.rf_scan_enabled
        else None
    )
    if interface and not settings.rf_scan_enabled:
        LOGGER.info("active RF scanning is disabled by configuration")

    spool = _telemetry_spool(settings)
    cutoff = datetime.now(UTC) - timedelta(hours=settings.telemetry_retention_hours)
    pruned = spool.prune_before(cutoff)
    if pruned:
        LOGGER.info("pruned %d expired local telemetry batches", pruned)

    rf_spool = _rf_scan_spool(settings)
    rf_cutoff = datetime.now(UTC) - timedelta(hours=settings.rf_scan_retention_hours)
    rf_pruned = rf_spool.prune_before(rf_cutoff)
    if rf_pruned:
        LOGGER.info("pruned %d expired local RF scans", rf_pruned)

    aggregator = TelemetryAggregator(settings.telemetry_window_seconds)
    sync_engine = TelemetrySyncEngine(settings, identity, spool)
    rf_sync_engine = RfScanSyncEngine(settings, identity, rf_spool)
    recording_controller = RecordingController(settings, identity, _database_path(settings))
    try:
        profile_runtime = ExperienceProfileRuntime(settings, identity)
    except (ValueError, OSError, KeyError) as exc:
        LOGGER.error("invalid saved experience profile: %s", exc)
        raise SystemExit(
            "Repair or remove data/agent/experience-profile.json before restarting"
        ) from exc
    recording_controller.configure_capture(
        profile_runtime.active.raw if profile_runtime.active else None
    )
    probe_runtime = profile_runtime.make_probes(interface) if interface else None
    pending_probe_observations: list[Observation] = []
    pending_probe_errors: list[str] = []
    probe_cache: dict[str, Observation] = {}
    probe_cache_ttl_seconds = max(
        profile_runtime.interval_seconds * 3,
        profile_runtime.timeout_seconds * 2,
    )
    last_gateway: str | None = None
    last_ipv4_address: str | None = None
    last_probe_context: dict[str, str] = {}

    LOGGER.info("agent started agent_id=%s server=%s", identity.agent_id, settings.server_url)
    next_heartbeat = 0.0
    next_collection = 0.0
    next_state = 0.0
    next_sync = 0.0
    next_probe = 0.0

    while True:
        recording_controller.stop_if_due()
        now = time.monotonic()
        if scan_runtime is not None:
            _service_rf_scan(scan_runtime, rf_spool, now)

        if probe_runtime is not None:
            probe_batch = probe_runtime.poll()
            if probe_batch is not None:
                _update_probe_cache(probe_cache, probe_batch.observations)
                pending_probe_observations.extend(probe_batch.observations)
                pending_probe_errors.extend(probe_batch.errors)

        if now >= next_heartbeat:
            try:
                heartbeat = _heartbeat(
                    settings,
                    identity,
                    recording_controller.heartbeat_payload(),
                )
                recording_controller.handle_commands(heartbeat.commands)
                try:
                    profile_runtime.receive(heartbeat.experience_profile)
                except (ValueError, TypeError) as exc:
                    LOGGER.warning("experience profile rejected: %s", exc)
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning("heartbeat failed: %s", exc)
            next_heartbeat = now + settings.heartbeat_interval_seconds

        if probe_runtime is not None and profile_runtime.pending and not probe_runtime.running:
            try:
                if profile_runtime.apply():
                    probe_runtime.close()
                    probe_runtime = profile_runtime.make_probes(interface)
                    probe_cache.clear()
                    next_probe = now
                    probe_cache_ttl_seconds = max(
                        profile_runtime.interval_seconds * 3, profile_runtime.timeout_seconds * 2
                    )
                    recording_controller.configure_capture(
                        profile_runtime.active.raw if profile_runtime.active else None
                    )
                    LOGGER.info("experience profile applied version=%s", profile_runtime.version)
            except OSError as exc:
                LOGGER.warning("experience profile could not be saved: %s", exc)

        if runtime is not None and now >= next_collection:
            extra_observations = _fresh_probe_observations(
                probe_cache,
                probe_cache_ttl_seconds,
            )
            if scan_runtime is not None:
                extra_observations.extend(scan_runtime.readiness_observations())

            cycle = runtime.collect_cycle(
                extra_observations=extra_observations,
                extra_collector_errors=pending_probe_errors,
            )
            gateway = cycle.snapshot.network.get("gateway")
            last_gateway = gateway if isinstance(gateway, str) else None
            ipv4_address = cycle.snapshot.network.get("ipv4_address")
            last_ipv4_address = ipv4_address if isinstance(ipv4_address, str) else None
            frequency = cycle.snapshot.wifi.get("frequency_mhz")
            band = (
                "unknown"
                if not isinstance(frequency, (float, int))
                else "2.4ghz"
                if frequency < 3000
                else "5ghz"
                if frequency < 5925
                else "6ghz"
            )
            last_probe_context = {
                "ssid": cycle.snapshot.wifi.get("ssid") or "",
                "band": band,
                "bssid": cycle.snapshot.wifi.get("bssid") or "",
            }
            if profile_runtime.version:
                for metric, metadata in cycle.snapshot.measurement_metadata.items():
                    if metric.startswith("wifi."):
                        metadata["profile_version"] = profile_runtime.version
            recording_observations = [*cycle.observations, *pending_probe_observations]
            telemetry_observations = [
                *cycle.observations,
                *cycle.derived_observations,
                *pending_probe_observations,
            ]
            collector_errors = list(cycle.snapshot.collector_errors)
            pending_probe_observations.clear()
            pending_probe_errors.clear()
            aggregator.consume(telemetry_observations)
            recording_controller.consume(
                recording_observations,
                observed_at=cycle.snapshot.observed_at,
                collector_errors=collector_errors,
            )

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

        if probe_runtime is not None and now >= next_probe:
            probe_runtime.start(last_gateway, last_ipv4_address, last_probe_context)
            next_probe = now + profile_runtime.interval_seconds

        if now >= next_sync:
            synced = sync_engine.sync_pending()
            if synced:
                LOGGER.info("telemetry batches synchronized count=%d", synced)
            rf_synced = rf_sync_engine.sync_pending()
            if rf_synced:
                LOGGER.info("RF scans synchronized count=%d", rf_synced)
            recording_synced = recording_controller.sync_pending()
            if recording_synced:
                LOGGER.info("recording batches synchronized count=%d", recording_synced)
            next_sync = now + settings.telemetry_sync_interval_seconds

        due = [next_heartbeat, next_sync]
        if runtime is not None:
            due.extend([next_collection, next_state])
        if probe_runtime is not None:
            due.append(next_probe)
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
    rf_spool = _rf_scan_spool(settings)

    if args.command == "enroll":
        identity = _enroll(settings, store, force=args.force)
        print(f"Enrolled agent: {identity.agent_id}")
        return

    if args.command == "status":
        _print_status(settings, store, spool, rf_spool)
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
