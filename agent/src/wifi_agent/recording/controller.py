import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from wifi_agent.config import AgentSettings
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.recording.client import RecordingApiClient
from wifi_agent.recording.context import set_active_recording_id
from wifi_agent.recording.counters import CounterDeltaProcessor
from wifi_agent.recording.store import RecordingStore
from wifi_agent.recording.survey import SurveyDeltaProcessor
from wifi_agent.storage import AgentIdentity

LOGGER = logging.getLogger("wifi_agent.recording")


class RecordingController:
    """Apply recording commands, capture raw observations and synchronize durable batches."""

    def __init__(
        self,
        settings: AgentSettings,
        identity: AgentIdentity,
        database_path: Path,
    ):
        self.capture_scope = None
        self.server_scope = settings.server_url.rstrip("/")
        self.capture_retention = 0
        self.identity = identity
        self.sample_interval_seconds = settings.telemetry_sample_interval_seconds
        self.client = RecordingApiClient(settings)
        self.store = RecordingStore(database_path)
        self.store.initialize()
        active = self.store.active()
        set_active_recording_id(active.recording_id if active else None)
        self._last_state: dict[str, Any] = {}
        self._counter_delta = CounterDeltaProcessor()
        self._survey_delta = SurveyDeltaProcessor()

    def heartbeat_payload(self) -> dict[str, Any]:
        active = self.store.active()
        return {
            "active": active is not None,
            "recording_id": active.recording_id if active else None,
        }

    def stop_if_due(self, now: datetime | None = None) -> bool:
        active = self.store.active()
        if active is None or active.deadline_at is None:
            return False
        now = now or datetime.now(UTC)
        if now < active.deadline_at:
            return False
        self.store.stop(active.recording_id, now)
        set_active_recording_id(None)
        LOGGER.info("recording duration reached recording_id=%s", active.recording_id)
        return True

    def handle_commands(self, commands: list[dict[str, Any]]) -> None:
        def priority(command):
            if command.get("type") == "recording.start":
                return 0
            if (
                command.get("type") == "recording.capture"
                and command.get("payload", {}).get("mode") == "automatic"
            ):
                return 1
            return 2

        for command in sorted(commands, key=priority):
            command_id = str(command.get("id", ""))
            command_type = str(command.get("type", ""))
            payload = command.get("payload") or {}
            if not command_id:
                continue

            try:
                if command_type == "recording.start":
                    self._start(command_id, payload)
                elif command_type == "recording.capture":
                    self._capture(command_id, payload)
                elif command_type == "recording.stop":
                    self._stop(command_id, payload)
                else:
                    self.client.acknowledge_command(
                        self.identity,
                        command_id,
                        status="failed",
                        message=f"unsupported command: {command_type}",
                    )
            except (RuntimeError, ValueError) as exc:
                LOGGER.warning("recording command failed command_id=%s error=%s", command_id, exc)
                self.client.acknowledge_command(
                    self.identity,
                    command_id,
                    status="failed",
                    message=str(exc),
                )

    def consume(
        self,
        observations: list[Observation],
        *,
        observed_at: datetime | None = None,
        collector_errors: list[str] | None = None,
    ) -> None:
        active = self.store.active()
        if active is None and self.capture_scope is None:
            return

        cycle_at = observed_at or datetime.now(UTC)
        metrics: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        observed_at = cycle_at
        metrics.append(
            {
                "observed_at": observed_at.isoformat(),
                "metric": "sensor.collection_cycle",
                "value": 1.0,
                "unit": None,
                "labels": {
                    "configured_interval_seconds": self.sample_interval_seconds,
                    "collector_errors_count": len(collector_errors or []),
                    **({"collector_errors": collector_errors or []} if self.capture_scope else {}),
                },
            }
        )

        derived = [
            *self._counter_delta.consume(observations),
            *self._survey_delta.consume(observations),
        ]
        observations = [*observations, *derived]
        for observation in observations:
            observed_at = max(observed_at, observation.observed_at)
            if observation.kind is ObservationKind.GAUGE:
                if isinstance(observation.value, bool) or not isinstance(
                    observation.value, (int, float)
                ):
                    continue
                if not math.isfinite(observation.value):
                    continue
                metrics.append(
                    {
                        "observed_at": observation.observed_at.isoformat(),
                        "metric": observation.metric,
                        "value": float(observation.value),
                        "unit": observation.unit,
                        "labels": {
                            **observation.labels,
                            **(
                                {"measurement": observation.metadata, "source": observation.source}
                                if self.capture_scope
                                else {}
                            ),
                        },
                    }
                )
                continue

            if observation.kind is not ObservationKind.STATE:
                continue

            if self.capture_scope:
                events.append(
                    {
                        "observed_at": observation.observed_at.isoformat(),
                        "event_type": "state.observation",
                        "severity": "info",
                        "data": {
                            "metric": observation.metric,
                            "current": observation.value,
                            "unit": observation.unit,
                            "labels": observation.labels,
                            "metadata": observation.metadata,
                        },
                    }
                )
            previous = self._last_state.get(observation.metric)
            if observation.metric not in self._last_state:
                event_type = "state.initial"
            elif previous == observation.value:
                continue
            else:
                event_type = "state.changed"

            events.append(
                {
                    "observed_at": observation.observed_at.isoformat(),
                    "event_type": event_type,
                    "severity": "info",
                    "data": {
                        "metric": observation.metric,
                        "previous": previous,
                        "current": observation.value,
                        "unit": observation.unit,
                        "labels": observation.labels,
                    },
                }
            )
            self._last_state[observation.metric] = observation.value

        if self.capture_scope:
            self.store.buffer_cycle(
                self.capture_scope, metrics, events, cycle_at, self.capture_retention
            )
        if active is None:
            return
        batch = self.store.enqueue(active.recording_id, metrics, events, observed_at)
        if batch is not None:
            LOGGER.info(
                "recording batch queued recording_id=%s sequence=%d metrics=%d events=%d",
                active.recording_id,
                batch.sequence,
                len(batch.metrics),
                len(batch.events),
            )

    def sync_pending(self, limit: int = 50) -> int:
        synced = 0
        for batch in self.store.pending(limit=limit):
            try:
                response = self.client.publish_batch(self.identity, batch)
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning(
                    "recording batch sync failed recording_id=%s sequence=%d error=%s",
                    batch.recording_id,
                    batch.sequence,
                    exc,
                )
                break
            if response.get("status") not in {"accepted", "already_accepted"}:
                LOGGER.warning(
                    "recording batch was not acknowledged batch_id=%s response=%s",
                    batch.batch_id,
                    response,
                )
                break
            self.store.acknowledge_batch(batch.batch_id)
            synced += 1

        for recording in self.store.recordings_waiting_for_manifest():
            if self.store.has_pending_batches(recording.recording_id):
                continue
            try:
                response = self.client.publish_manifest(self.identity, recording)
            except (httpx.HTTPError, OSError) as exc:
                LOGGER.warning(
                    "recording manifest sync failed recording_id=%s error=%s",
                    recording.recording_id,
                    exc,
                )
                continue
            if response.get("sync_status") == "complete":
                self.store.acknowledge_manifest(recording.recording_id)
                LOGGER.info("recording synchronized recording_id=%s", recording.recording_id)
            else:
                LOGGER.warning(
                    "recording manifest incomplete recording_id=%s response=%s",
                    recording.recording_id,
                    response,
                )
        return synced

    def _start(self, command_id: str, payload: dict[str, Any]) -> None:
        recording_id = str(payload.get("recording_id", ""))
        if not recording_id:
            raise ValueError("recording.start is missing recording_id")
        max_duration_minutes = payload.get("max_duration_minutes")
        if max_duration_minutes is not None and (
            isinstance(max_duration_minutes, bool)
            or not isinstance(max_duration_minutes, int)
            or not 1 <= max_duration_minutes <= 1440
        ):
            raise ValueError("recording.start max_duration_minutes must be between 1 and 1440")
        active = self.store.active()
        if active is not None and active.recording_id != recording_id:
            raise RuntimeError(f"recording {active.recording_id} is already active")

        started_at = datetime.now(UTC)
        recording = self.store.start(recording_id, started_at, max_duration_minutes)
        set_active_recording_id(recording.recording_id)
        self._last_state.clear()
        self._counter_delta.reset()
        self._survey_delta.reset()
        self.client.acknowledge_command(
            self.identity,
            command_id,
            status="acked",
            data={
                "recording_id": recording.recording_id,
                "started_at": recording.started_at.isoformat(),
            },
        )
        LOGGER.info("diagnostic recording started recording_id=%s", recording.recording_id)

    def _stop(self, command_id: str, payload: dict[str, Any]) -> None:
        recording_id = str(payload.get("recording_id", ""))
        if not recording_id:
            raise ValueError("recording.stop is missing recording_id")
        ended_at = datetime.now(UTC)
        recording = self.store.stop(recording_id, ended_at)
        set_active_recording_id(None)
        self.client.acknowledge_command(
            self.identity,
            command_id,
            status="acked",
            data={
                "recording_id": recording.recording_id,
                "ended_at": recording.ended_at.isoformat() if recording.ended_at else None,
            },
        )
        LOGGER.info("diagnostic recording stopped recording_id=%s", recording.recording_id)

    def configure_capture(self, profile: dict | None) -> None:
        policy = (profile or {}).get("profile", {})
        enabled = policy.get("enabled") is True and policy.get("automatic_capture") is True
        scope = (
            f"{self.server_scope}:{self.identity.agent_id}:{profile['version']}"
            if enabled
            else None
        )
        if self.capture_scope is not None and scope != self.capture_scope or not enabled:
            self.store.clear_buffer()
        self.capture_scope = scope
        self.capture_retention = min(
            630,
            max(0, int(policy.get("capture_pre_seconds", 120)))
            + max(0, int(policy.get("confirm_seconds", 15)))
            + 30,
        )

    def _capture(self, command_id: str, payload: dict) -> None:
        expected = f"{self.server_scope}:{self.identity.agent_id}:{payload.get('profile_version')}"
        # A persisted successful command remains retryable even after a policy edit.
        if self.capture_scope != expected:
            import sqlite3

            with sqlite3.connect(self.store.database_path) as connection:
                saved = connection.execute(
                    "SELECT result FROM capture_commands WHERE command_id = ?", (command_id,)
                ).fetchone()
            if not saved:
                raise ValueError("Capture profile is disabled or has changed")
        recording_id = payload.get("recording_id")
        if (
            not isinstance(recording_id, str)
            or not recording_id
            or payload.get("mode") not in ("automatic", "reused")
        ):
            raise ValueError("Invalid capture recording or mode")
        try:
            start, end = (
                datetime.fromisoformat(payload[key]) for key in ("window_start", "window_end")
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid capture window") from exc
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or not 0 < (end - start).total_seconds() <= 1500
        ):
            raise ValueError("Invalid capture window")
        result = self.store.capture(
            command_id, recording_id, expected, start, end, datetime.now(UTC), payload["mode"]
        )
        active = self.store.active()
        set_active_recording_id(active.recording_id if active else None)
        self.client.acknowledge_command(self.identity, command_id, status="acked", data=result)
