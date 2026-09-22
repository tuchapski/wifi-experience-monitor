import argparse

import uvicorn

from wem.api.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wi-Fi Experience Monitor API")
    parser.add_argument("--database", default="data/wem.db", help="SQLite database path")
    parser.add_argument("--host", default="127.0.0.1", help="API listen address")
    parser.add_argument("--port", type=int, default=8000, help="API listen port")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    uvicorn.run(create_app(args.database), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
