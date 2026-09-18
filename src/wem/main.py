import argparse
import json

from wem.collectors.network import NetworkCollector
from wem.collectors.wifi import WifiCollector
from wem.models.metrics import SensorSnapshot


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

    errors = [
        *wifi_collector.errors,
        *network_collector.errors,
    ]

    snapshot = SensorSnapshot.create(
        wifi=wifi_metrics,
        network=network_metrics,
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
