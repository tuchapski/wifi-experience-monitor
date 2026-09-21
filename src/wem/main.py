import argparse

from wem.runtime.console import ConsoleSensorRuntime
from wem.runtime.sensor import RuntimeConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=("Wi-Fi Experience Monitor sensor"))

    parser.add_argument(
        "--interface",
        required=True,
        help=("Wireless interface to monitor"),
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help=("Collection interval in seconds"),
    )

    parser.add_argument(
        "--database",
        default="data/wem.db",
        help=("SQLite database path"),
    )

    return parser


def main() -> None:
    parser = build_parser()

    args = parser.parse_args()

    config = RuntimeConfig(
        interface=args.interface,
        interval_seconds=args.interval,
    )

    runtime = ConsoleSensorRuntime(
        config=config,
        database_path=args.database,
    )

    runtime.run_forever()


if __name__ == "__main__":
    main()
