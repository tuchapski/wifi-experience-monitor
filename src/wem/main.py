import argparse
import json

from wem.collectors.network import NetworkCollector
from wem.collectors.wifi import WifiCollector
from wem.models.metrics import SensorSnapshot
from wem.tests_engine.connectivity import ConnectivityTester


def main() -> None:
    parser = argparse.ArgumentParser(description="Wi-Fi Experience Monitor")

    parser.add_argument(
        "--interface",
        default="wlp0s20f3",
        help="Wi-Fi interface to monitor",
    )

    args = parser.parse_args()

    wifi_collector = WifiCollector(args.interface)

    network_collector = NetworkCollector(args.interface)

    wifi_metrics = wifi_collector.collect()
    network_metrics = network_collector.collect()

    connectivity_tester = ConnectivityTester(
        interface=args.interface,
        gateway=network_metrics.gateway,
    )

    connectivity_metrics = connectivity_tester.run()

    errors = [
        *wifi_collector.errors,
        *network_collector.errors,
        *connectivity_tester.errors,
    ]

    snapshot = SensorSnapshot.create(
        wifi=wifi_metrics,
        network=network_metrics,
        connectivity=connectivity_metrics,
        errors=errors,
    )

    print(
        json.dumps(
            snapshot.to_dict(),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
