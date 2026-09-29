from dataclasses import dataclass

from wifi_agent.collectors import NetworkStateCollector, WifiStateCollector
from wifi_agent.core import Observation, ObservationKind
from wifi_agent.processors import CurrentStateSnapshot, StateProcessor
from wifi_agent.recording.counters import CounterDeltaProcessor
from wifi_agent.recording.survey import SurveyDeltaProcessor


@dataclass(frozen=True, slots=True)
class CollectionCycle:
    observations: list[Observation]
    derived_observations: list[Observation]
    snapshot: CurrentStateSnapshot


class CurrentStateRuntime:
    def __init__(self, interface: str, sample_interval_seconds: float = 1.0):
        self.interface = interface
        self.wifi = WifiStateCollector(interface)
        self.network = NetworkStateCollector(interface)
        self.processor = StateProcessor()
        self.counter_delta = CounterDeltaProcessor()
        self.survey_delta = SurveyDeltaProcessor()
        self.maximum_link_interval_seconds = max(5.0, sample_interval_seconds * 3)

    def _survey_readiness(self, observations: list[Observation]) -> list[Observation]:
        observed_at = max((item.observed_at for item in observations), default=None)
        if observed_at is None:
            return []

        values = {item.metric: item.value for item in observations}
        connected = values.get("wifi.connected")
        frequency = values.get("wifi.frequency_mhz")
        width = values.get("wifi.channel_width_mhz")
        active = values.get("wifi.survey_active_ms")
        busy = values.get("wifi.survey_busy_ms")

        if connected is not True:
            status = "not_observable"
            reason = "RF survey requires an active Wi-Fi association."
        elif frequency is None:
            status = "degraded"
            reason = "Connected frequency is unavailable, so RF survey cannot be validated."
        elif width is None:
            status = "degraded"
            reason = "Channel width is unavailable, so interval utilization cannot be derived."
        elif active is None:
            status = "unavailable"
            reason = "The driver did not expose channel active time for the associated frequency."
        elif busy is None:
            status = "degraded"
            reason = "The driver reports channel active time but not channel busy time."
        else:
            status = "verified"
            reason = "Driver reports active and busy channel counters for the associated frequency."

        labels = {"interface": self.interface}
        return [
            Observation(
                source="wifi-readiness",
                kind=ObservationKind.STATE,
                metric="wifi.survey_status",
                value=status,
                observed_at=observed_at,
                labels=labels,
            ),
            Observation(
                source="wifi-readiness",
                kind=ObservationKind.STATE,
                metric="wifi.survey_reason",
                value=reason,
                observed_at=observed_at,
                labels=labels,
            ),
        ]

    def collect_cycle(
        self,
        *,
        extra_observations: list[Observation] | None = None,
        extra_collector_errors: list[str] | None = None,
    ) -> CollectionCycle:
        observations = [*self.wifi.collect(), *self.network.collect()]
        # Recording derives its own deltas from the raw observations.
        link_deltas = [
            delta
            for delta in self.counter_delta.consume(observations)
            if float(delta.labels.get("interval_seconds", "inf"))
            <= self.maximum_link_interval_seconds
        ]
        survey_deltas = self.survey_delta.consume(observations)
        readiness = self._survey_readiness(observations)
        derived_observations = [*link_deltas, *survey_deltas, *readiness]
        snapshot = self.processor.build(
            [
                *observations,
                *derived_observations,
                *(extra_observations or []),
            ],
            collector_errors=[
                *self.wifi.errors,
                *self.network.errors,
                *(extra_collector_errors or []),
            ],
        )
        return CollectionCycle(
            observations=observations,
            derived_observations=derived_observations,
            snapshot=snapshot,
        )

    def collect(self) -> CurrentStateSnapshot:
        return self.collect_cycle().snapshot
