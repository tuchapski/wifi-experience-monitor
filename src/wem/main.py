import argparse
import json

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

    collector = WifiCollector(args.interface)

    wifi_metrics = collector.collect()

    snapshot = SensorSnapshot.create(
        wifi=wifi_metrics,
        errors=collector.errors,
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
