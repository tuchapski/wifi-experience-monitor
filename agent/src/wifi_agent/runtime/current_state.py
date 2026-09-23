from dataclasses import dataclass

from wifi_agent.collectors import NetworkStateCollector, WifiStateCollector
from wifi_agent.core import Observation
from wifi_agent.processors import CurrentStateSnapshot, StateProcessor


@dataclass(frozen=True, slots=True)
class CollectionCycle:
    observations: list[Observation]
    snapshot: CurrentStateSnapshot


class CurrentStateRuntime:
    def __init__(self, interface: str):
        self.interface = interface
        self.wifi = WifiStateCollector(interface)
        self.network = NetworkStateCollector(interface)
        self.processor = StateProcessor()

    def collect_cycle(self) -> CollectionCycle:
        observations = [*self.wifi.collect(), *self.network.collect()]
        snapshot = self.processor.build(
            observations,
            collector_errors=[*self.wifi.errors, *self.network.errors],
        )
        return CollectionCycle(observations=observations, snapshot=snapshot)

    def collect(self) -> CurrentStateSnapshot:
        return self.collect_cycle().snapshot
