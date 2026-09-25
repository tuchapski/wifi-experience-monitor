from dataclasses import dataclass

from wifi_agent.collectors import NetworkStateCollector, WifiStateCollector
from wifi_agent.core import Observation
from wifi_agent.processors import CurrentStateSnapshot, StateProcessor
from wifi_agent.recording.counters import CounterDeltaProcessor


@dataclass(frozen=True, slots=True)
class CollectionCycle:
    observations: list[Observation]
    snapshot: CurrentStateSnapshot


class CurrentStateRuntime:
    def __init__(self, interface: str, sample_interval_seconds: float = 1.0):
        self.interface = interface
        self.wifi = WifiStateCollector(interface)
        self.network = NetworkStateCollector(interface)
        self.processor = StateProcessor()
        self.counter_delta = CounterDeltaProcessor()
        self.maximum_link_interval_seconds = max(5.0, sample_interval_seconds * 3)

    def collect_cycle(self) -> CollectionCycle:
        observations = [*self.wifi.collect(), *self.network.collect()]
        # Recording derives its own deltas from the raw observations.
        link_deltas = [
            delta
            for delta in self.counter_delta.consume(observations)
            if float(delta.labels.get("interval_seconds", "inf"))
            <= self.maximum_link_interval_seconds
        ]
        snapshot = self.processor.build(
            [*observations, *link_deltas],
            collector_errors=[*self.wifi.errors, *self.network.errors],
        )
        return CollectionCycle(observations=observations, snapshot=snapshot)

    def collect(self) -> CurrentStateSnapshot:
        return self.collect_cycle().snapshot
