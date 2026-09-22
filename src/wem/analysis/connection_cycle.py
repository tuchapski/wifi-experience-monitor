from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

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


@dataclass(slots=True)
class _Observation:
    observed_at: datetime
    ssid: str | None
    bssid: str | None
    connected_time_seconds: int | None
    connected: bool


class ConnectionCycleTracker:
    """Track observable connection lifecycle transitions without inventing exact timings.

    Timing is derived from periodic samples. When a transition is known only to have
    happened between two samples, elapsed values are explicitly marked as estimates.
    A sensor that starts while Wi-Fi is already connected creates an
    ``observed_existing`` session and leaves elapsed timings unknown.
    """

    def __init__(self) -> None:
        self._previous: _Observation | None = None
        self._current: ConnectionCycleMetrics | None = None
        self._ever_connected = False

    def observe(
        self,
        wifi: WifiMetrics,
        network: NetworkMetrics,
        connectivity: ConnectivityMetrics,
        observed_at: datetime | None = None,
    ) -> ConnectionCycleMetrics | None:
        now = self._utc(observed_at or datetime.now(UTC))
        connected = self._is_connected(wifi)
        observation = _Observation(
            observed_at=now,
            ssid=wifi.ssid,
            bssid=wifi.bssid,
            connected_time_seconds=wifi.connected_time_seconds,
            connected=connected,
        )
        resolution_ms = self._resolution_ms(now)

        if not connected:
            result = self._observe_disconnected(now, resolution_ms)
            self._previous = observation
            return result

        session_type = self._transition_type(observation)
        if self._current is None or self._current.state == "disconnected" or session_type:
            self._current = self._new_cycle(
                observation,
                session_type or ("reconnect" if self._ever_connected else "initial_connect"),
                resolution_ms,
            )

        self._ever_connected = True
        self._update_cycle(self._current, wifi, network, connectivity, now, resolution_ms)
        self._previous = observation
        return self._current

    def _observe_disconnected(
        self,
        now: datetime,
        resolution_ms: float | None,
    ) -> ConnectionCycleMetrics | None:
        if self._current is None:
            return None
        if self._current.state != "disconnected":
            self._current.state = "disconnected"
            self._current.completed_at = now.isoformat()
            self._current.last_observed_at = now.isoformat()
            self._current.sample_resolution_ms = resolution_ms
            self._current.limitations = self._limitations(self._current.session_type)
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
    ) -> ConnectionCycleMetrics:
        observed_existing = session_type == "observed_existing"
        started_at = None
        if not observed_existing:
            started_at = (
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
            started_at=started_at,
            last_observed_at=observation.observed_at.isoformat(),
            completed_at=None,
            total_time_ms=None,
            sample_resolution_ms=resolution_ms,
            stages={
                key: ConnectionStageMetric(
                    status="pending",
                    observed_at=None,
                    elapsed_ms=None,
                    estimated=False,
                    reason=f"{label} has not been observed in this session.",
                )
                for key, label in _STAGE_LABELS.items()
            },
            limitations=self._limitations(session_type),
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

        associated = self._is_connected(wifi)
        dhcp_ready = bool(network.ipv4_address)
        gateway_ready = connectivity.gateway_reachable
        dns_ready = connectivity.dns_success
        authentication_ok = wifi.authenticated is not False
        authorization_ok = wifi.authorized is not False
        network_ready = (
            associated
            and authentication_ok
            and authorization_ok
            and dhcp_ready
            and gateway_ready is True
            and dns_ready is True
        )

        values: dict[str, bool | None] = {
            "association": associated,
            "authentication": wifi.authenticated,
            "authorization": wifi.authorized,
            "dhcp": dhcp_ready,
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
    def _limitations(session_type: str) -> list[str]:
        base = [
            "Connection-cycle timing is derived from periodic samples, not packet-level "
            "or NetworkManager event timestamps.",
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
