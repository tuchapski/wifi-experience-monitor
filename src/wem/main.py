import argparse

from wem.runtime.console import ConsoleSensorRuntime
from wem.runtime.sensor import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Wi-Fi Experience Monitor")

    parser.add_argument(
        "--interface",
        default="wlp0s20f3",
        help="Wi-Fi interface to monitor",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Collection interval in seconds",
    )

    args = parser.parse_args()

    config = RuntimeConfig(
        interface=args.interface,
        interval_seconds=args.interval,
    )

    runtime = ConsoleSensorRuntime(config)

    try:
        runtime.run_forever()
    except KeyboardInterrupt:
        print("\nSensor stopped.")


if __name__ == "__main__":
    main()
