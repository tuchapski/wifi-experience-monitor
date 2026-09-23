from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from wem.collectors.networkmanager_events import (
    NetworkManagerDeviceEvent,
    networkmanager_state_name,
)
from wem.models.metrics import (
    ConnectionCycleMetrics,
    ConnectionStageMetric,
    ConnectivityMetrics,
    NetworkMetrics,
    WifiMetrics,
)

_STAGE_LABELS = {
    "association": "Wi-Fi association",
    "authentication": "802.11 authentication",
    "authorization": "802.11 authorization",
    "dhcp": "IPv4 address available",
    "gateway": "Gateway reachable",
    "dns": "DNS resolution",
    "network_ready": "Network ready",
}

_NM_ACTIVE_OR_ACTIVATING_STATES = {40, 50, 60, 70, 80, 90, 100}
_NM_START_STATES = {40, 50, 60, 70}
_NM_DISCONNECTED_STATES = {10, 20, 30, 120}


@dataclass(slots=True)
class _Observation:
    observed_at: datetime
    ssid: str | None
    bssid: str | None
    connected_time_seconds: int | None
    connected: bool


class ConnectionCycleTracker:
    """Track connection lifecycle transitions using D-Bus events plus periodic samples.

    NetworkManager device-state signals provide event timestamps for activation start,
    layer-2 completion and IPv4 configuration completion. Wi-Fi authentication,
    authorization, gateway, DNS and final network readiness still use sampled evidence
    when NetworkManager does not expose a stage-specific boundary.
    """

    def __init__(self) -> None:
        self._previous: _Observation | None = None
        self._current: ConnectionCycleMetrics | None = None
        self._ever_connected = False

        self._nm_activation_id = 0
        self._applied_nm_activation_id = 0
        self._nm_started_at: datetime | None = None
        self._nm_l2_ready_at: datetime | None = None
        self._nm_ipv4_ready_at: datetime | None = None
        self._nm_disconnected_at: datetime | None = None
        self._nm_last_state: int | None = None
        self._nm_event_count = 0
        self._event_monitor_status = "unavailable"
        self._event_monitor_reason: str | None = None

    def observe(
        self,
        wifi: WifiMetrics,
        network: NetworkMetrics,
        connectivity: ConnectivityMetrics,
        observed_at: datetime | None = None,
        networkmanager_events: Sequence[NetworkManagerDeviceEvent] = (),
        event_monitor_status: str = "unavailable",
        event_monitor_reason: str | None = None,
    ) -> ConnectionCycleMetrics | None:
        now = self._utc(observed_at or datetime.now(UTC))
        self._consume_networkmanager_events(
            networkmanager_events,
            status=event_monitor_status,
            reason=event_monitor_reason,
        )

        connected = self._is_connected(wifi)
        observation = _Observation(
            observed_at=now,
            ssid=wifi.ssid,
            bssid=wifi.bssid,
            connected_time_seconds=wifi.connected_time_seconds,
            connected=connected,
        )
        resolution_ms = self._resolution_ms(now)

        event_cycle_started = self._start_event_cycle_if_needed(
            observation,
            resolution_ms,
        )

        if not connected:
            if (
                self._current is not None
                and self._current.timing_source == "networkmanager_dbus+sampling"
                and self._nm_last_state in _NM_ACTIVE_OR_ACTIVATING_STATES
            ):
                self._update_networkmanager_metadata(self._current)
                self._apply_networkmanager_stages(self._current)
                self._current.last_observed_at = now.isoformat()
                self._current.sample_resolution_ms = resolution_ms
                self._previous = observation
                return self._current

            result = self._observe_disconnected(now, resolution_ms)
            self._previous = observation
            return result

        session_type = self._transition_type(observation)
        if not event_cycle_started and (
            self._current is None or self._current.state == "disconnected" or session_type
        ):
            self._current = self._new_cycle(
                observation,
                session_type or ("reconnect" if self._ever_connected else "initial_connect"),
                resolution_ms,
            )

        self._ever_connected = True
        assert self._current is not None
        self._update_cycle(self._current, wifi, network, connectivity, now, resolution_ms)
        self._previous = observation
        return self._current

    def _consume_networkmanager_events(
        self,
        events: Sequence[NetworkManagerDeviceEvent],
        *,
        status: str,
        reason: str | None,
    ) -> None:
        self._event_monitor_status = status
        self._event_monitor_reason = reason

        for event in sorted(events, key=lambda item: item.observed_at):
            observed_at = self._utc(event.observed_at)
            self._nm_last_state = event.new_state
            self._nm_event_count += 1

            if event.old_state == 100:
                self._ever_connected = True

            if event.new_state in _NM_START_STATES and (
                event.old_state <= 30 or event.old_state >= 100
            ):
                self._nm_activation_id += 1
                self._nm_started_at = observed_at
                self._nm_l2_ready_at = None
                self._nm_ipv4_ready_at = None
                self._nm_disconnected_at = None

            if self._nm_started_at is not None:
                if self._nm_l2_ready_at is None and 70 <= event.new_state <= 100:
                    self._nm_l2_ready_at = observed_at
                if self._nm_ipv4_ready_at is None and 80 <= event.new_state <= 100:
                    self._nm_ipv4_ready_at = observed_at

            if event.new_state in _NM_DISCONNECTED_STATES:
                self._nm_disconnected_at = observed_at

    def _start_event_cycle_if_needed(
        self,
        observation: _Observation,
        resolution_ms: float | None,
    ) -> bool:
        if (
            self._nm_activation_id == 0
            or self._nm_activation_id == self._applied_nm_activation_id
            or self._nm_started_at is None
        ):
            return False

        session_type = "reconnect" if self._ever_connected else "initial_connect"
        self._current = self._new_cycle(
            observation,
            session_type,
            resolution_ms,
            started_at=self._nm_started_at,
            timing_source="networkmanager_dbus+sampling",
        )
        self._applied_nm_activation_id = self._nm_activation_id
        self._update_networkmanager_metadata(self._current)
        self._apply_networkmanager_stages(self._current)
        return True

    def _observe_disconnected(
        self,
        now: datetime,
        resolution_ms: float | None,
    ) -> ConnectionCycleMetrics | None:
        if self._current is None:
            return None
        if self._current.state != "disconnected":
            completed_at = now
            if (
                self._current.timing_source == "networkmanager_dbus+sampling"
                and self._nm_disconnected_at is not None
            ):
                completed_at = self._nm_disconnected_at
            self._current.state = "disconnected"
            self._current.completed_at = completed_at.isoformat()
            self._current.last_observed_at = now.isoformat()
            self._current.sample_resolution_ms = resolution_ms
            self._update_networkmanager_metadata(self._current)
            self._current.limitations = self._limitations(
                self._current.session_type,
                event_driven=self._current.timing_source == "networkmanager_dbus+sampling",
            )
        return self._current

    def _transition_type(self, current: _Observation) -> str | None:
        previous = self._previous
        if previous is None:
            return "observed_existing"
        if not previous.connected:
            return "reconnect" if self._ever_connected else "initial_connect"
        if previous.ssid is not None and current.ssid is not None and previous.ssid != current.ssid:
            return "network_change"
        if (
            previous.bssid is not None
            and current.bssid is not None
            and previous.bssid != current.bssid
        ):
            return "roam"
        if (
            previous.connected_time_seconds is not None
            and current.connected_time_seconds is not None
            and current.connected_time_seconds < previous.connected_time_seconds
        ):
            return "reassociation"
        return None

    def _new_cycle(
        self,
        observation: _Observation,
        session_type: str,
        resolution_ms: float | None,
        *,
        started_at: datetime | None = None,
        timing_source: str = "sampling",
    ) -> ConnectionCycleMetrics:
        observed_existing = session_type == "observed_existing"
        cycle_started_at: str | None = None
        if started_at is not None:
            cycle_started_at = self._utc(started_at).isoformat()
        elif not observed_existing:
            cycle_started_at = (
                self._previous.observed_at.isoformat()
                if self._previous is not None
                else observation.observed_at.isoformat()
            )
        return ConnectionCycleMetrics(
            session_id=uuid4().hex,
            session_type=session_type,
            state="connecting",
            ssid=observation.ssid,
            bssid=observation.bssid,
            started_at=cycle_started_at,
            last_observed_at=observation.observed_at.isoformat(),
            completed_at=None,
            total_time_ms=None,
            sample_resolution_ms=resolution_ms,
            timing_source=timing_source,
            event_monitor_status=self._event_monitor_status,
            event_monitor_reason=self._event_monitor_reason,
            networkmanager_state=self._nm_last_state,
            networkmanager_state_name=networkmanager_state_name(self._nm_last_state),
            networkmanager_event_count=self._nm_event_count,
            stages={
                key: ConnectionStageMetric(
                    status="pending",
                    observed_at=None,
                    elapsed_ms=None,
                    estimated=False,
                    reason=f"{label} has not been observed in this session.",
                    source="sampling",
                )
                for key, label in _STAGE_LABELS.items()
            },
            limitations=self._limitations(
                session_type,
                event_driven=timing_source == "networkmanager_dbus+sampling",
            ),
        )

    def _update_cycle(
        self,
        cycle: ConnectionCycleMetrics,
        wifi: WifiMetrics,
        network: NetworkMetrics,
        connectivity: ConnectivityMetrics,
        now: datetime,
        resolution_ms: float | None,
    ) -> None:
        cycle.ssid = wifi.ssid
        cycle.bssid = wifi.bssid
        cycle.last_observed_at = now.isoformat()
        cycle.sample_resolution_ms = resolution_ms

        self._update_networkmanager_metadata(cycle)
        self._apply_networkmanager_stages(cycle)

        associated = self._is_connected(wifi)
        ipv4_ready = bool(network.ipv4_address)
        gateway_ready = connectivity.gateway_reachable
        dns_ready = connectivity.dns_success
        authentication_ok = wifi.authenticated is not False
        authorization_ok = wifi.authorized is not False
        network_ready = (
            associated
            and authentication_ok
            and authorization_ok
            and ipv4_ready
            and gateway_ready is True
            and dns_ready is True
        )

        values: dict[str, bool | None] = {
            "association": associated,
            "authentication": wifi.authenticated,
            "authorization": wifi.authorized,
            "dhcp": ipv4_ready,
            "gateway": gateway_ready,
            "dns": dns_ready,
            "network_ready": network_ready,
        }

        for key, value in values.items():
            self._observe_stage(cycle, key, value, now)

        ready_stage = cycle.stages["network_ready"]
        if ready_stage.status == "observed":
            cycle.state = "ready"
            if cycle.total_time_ms is None:
                cycle.total_time_ms = ready_stage.elapsed_ms
        else:
            cycle.state = "connecting"

    def _update_networkmanager_metadata(self, cycle: ConnectionCycleMetrics) -> None:
        cycle.event_monitor_status = self._event_monitor_status
        cycle.event_monitor_reason = self._event_monitor_reason
        cycle.networkmanager_state = self._nm_last_state
        cycle.networkmanager_state_name = networkmanager_state_name(self._nm_last_state)
        cycle.networkmanager_event_count = self._nm_event_count

    def _apply_networkmanager_stages(self, cycle: ConnectionCycleMetrics) -> None:
        if (
            cycle.timing_source != "networkmanager_dbus+sampling"
            or cycle.started_at is None
            or self._nm_started_at is None
            or cycle.started_at != self._nm_started_at.isoformat()
        ):
            return

        if self._nm_l2_ready_at is not None:
            self._observe_event_stage(
                cycle,
                "association",
                self._nm_l2_ready_at,
                "NetworkManager entered IP_CONFIG; its layer-2 activation phase had completed.",
            )
        if self._nm_ipv4_ready_at is not None:
            self._observe_event_stage(
                cycle,
                "dhcp",
                self._nm_ipv4_ready_at,
                "NetworkManager left IP_CONFIG, indicating IP configuration completed. "
                "This does not prove DHCP was used; static IPv4 follows the same phase boundary.",
            )

    def _observe_event_stage(
        self,
        cycle: ConnectionCycleMetrics,
        key: str,
        observed_at: datetime,
        reason: str,
    ) -> None:
        stage = cycle.stages[key]
        started_at = cycle.started_at
        if stage.status == "observed" or started_at is None:
            return

        started = datetime.fromisoformat(started_at)
        event_time = self._utc(observed_at)
        stage.status = "observed"
        stage.observed_at = event_time.isoformat()
        stage.elapsed_ms = round(
            max(0.0, (event_time - started).total_seconds() * 1000.0),
            3,
        )
        stage.estimated = False
        stage.source = "networkmanager_dbus"
        stage.reason = (
            f"{reason} The timestamp is the D-Bus phase transition observed by the sensor, "
            "not an 802.11 packet timestamp."
        )

    def _observe_stage(
        self,
        cycle: ConnectionCycleMetrics,
        key: str,
        value: bool | None,
        now: datetime,
    ) -> None:
        stage = cycle.stages[key]
        if stage.status == "observed":
            return

        stage.source = "sampling"
        if value is None:
            stage.status = "unavailable"
            stage.reason = f"{_STAGE_LABELS[key]} is not exposed by the current measurement."
            return
        if value is False:
            stage.status = "pending"
            stage.reason = f"{_STAGE_LABELS[key]} is not currently observed."
            return

        stage.status = "observed"
        stage.observed_at = now.isoformat()
        started_at = cycle.started_at
        if started_at is None:
            stage.elapsed_ms = None
            stage.estimated = False
            stage.reason = (
                f"{_STAGE_LABELS[key]} is present, but the sensor did not observe "
                "the beginning of this connection session."
            )
            return

        started = datetime.fromisoformat(started_at)
        stage.elapsed_ms = round(max(0.0, (now - started).total_seconds() * 1000.0), 3)
        stage.estimated = True
        stage.reason = (
            f"{_STAGE_LABELS[key]} was first seen in a periodic sample; elapsed time "
            "is an upper-bound estimate constrained by the sampling interval."
        )

    def _resolution_ms(self, now: datetime) -> float | None:
        if self._previous is None:
            return None
        return round(max(0.0, (now - self._previous.observed_at).total_seconds() * 1000.0), 3)

    @staticmethod
    def _is_connected(wifi: WifiMetrics) -> bool:
        if wifi.associated is not None:
            return wifi.associated
        return wifi.bssid is not None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _limitations(session_type: str, *, event_driven: bool = False) -> list[str]:
        if event_driven:
            base = [
                "NetworkManager D-Bus timestamps identify activation phase boundaries, "
                "not packet-level 802.11 frame timestamps.",
                "Authentication, authorization, gateway, DNS and final network readiness "
                "can still be sampling upper bounds when no stage-specific event is available.",
                "A missing authentication or authorization value means unavailable telemetry, "
                "not failure.",
            ]
        else:
            base = [
                "Connection-cycle timing is derived from periodic samples when no matching "
                "NetworkManager activation event was observed.",
                "Estimated elapsed times are upper bounds limited by the sampling interval.",
                "A missing authentication or authorization value means unavailable telemetry, "
                "not failure.",
            ]
        if session_type == "observed_existing":
            base.append(
                "Monitoring started after this connection was already established, so stage "
                "durations are unknown."
            )
        if session_type == "roam":
            base.append(
                "During roaming, IPv4, gateway and DNS may remain continuously available; "
                "their presence does not prove those steps were repeated."
            )
        return base
