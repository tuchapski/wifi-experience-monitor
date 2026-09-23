from wifi_agent.collectors import NetworkStateCollector, WifiStateCollector
from wifi_agent.processors import CurrentStateSnapshot, StateProcessor


class CurrentStateRuntime:
    def __init__(self, interface: str):
        self.interface = interface
        self.wifi = WifiStateCollector(interface)
        self.network = NetworkStateCollector(interface)
        self.processor = StateProcessor()

    def collect(self) -> CurrentStateSnapshot:
        observations = [*self.wifi.collect(), *self.network.collect()]
        return self.processor.build(
            observations,
            collector_errors=[*self.wifi.errors, *self.network.errors],
        )
