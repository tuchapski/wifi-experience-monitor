import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from wifi_agent.config import AgentSettings
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.recording.client import RecordingApiClient
from wifi_agent.recording.counters import CounterDeltaProcessor
from wifi_agent.recording.store import RecordingStore
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
        self.identity = identity
        self.client = RecordingApiClient(settings)
        self.store = RecordingStore(database_path)
        self.store.initialize()
        self._last_state: dict[str, Any] = {}
        self._counter_delta = CounterDeltaProcessor()

    def heartbeat_payload(self) -> dict[str, Any]:
        active = self.store.active()
        return {
            "active": active is not None,
            "recording_id": active.recording_id if active else None,
        }

    def handle_commands(self, commands: list[dict[str, Any]]) -> None:
        for command in commands:
            command_id = str(command.get("id", ""))
            command_type = str(command.get("type", ""))
            payload = command.get("payload") or {}
            if not command_id:
                continue

            try:
                if command_type == "recording.start":
                    self._start(command_id, payload)
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

    def consume(self, observations: list[Observation]) -> None:
        active = self.store.active()
        if active is None:
            return

        metrics: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        observed_at = datetime.now(UTC)

        observations = [*observations, *self._counter_delta.consume(observations)]
        for observation in observations:
            observed_at = max(observed_at, observation.observed_at)
            if observation.kind is ObservationKind.GAUGE:
                if isinstance(observation.value, bool) or not isinstance(
                    observation.value, (int, float)
                ):
                    continue
                metrics.append(
                    {
                        "observed_at": observation.observed_at.isoformat(),
                        "metric": observation.metric,
                        "value": float(observation.value),
                        "unit": observation.unit,
                        "labels": observation.labels,
                    }
                )
                continue

            if observation.kind is not ObservationKind.STATE:
                continue

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
        active = self.store.active()
        if active is not None and active.recording_id != recording_id:
            raise RuntimeError(f"recording {active.recording_id} is already active")

        started_at = datetime.now(UTC)
        recording = self.store.start(recording_id, started_at)
        self._last_state.clear()
        self._counter_delta.reset()
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
