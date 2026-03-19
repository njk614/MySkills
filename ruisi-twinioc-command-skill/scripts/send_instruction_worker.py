from __future__ import annotations

import argparse
import time

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Background sender for TwinEasy SendInstruction")
    parser.add_argument("--token", required=True)
    parser.add_argument("--json-data", required=True)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--server-url", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.delay_seconds > 0:
        time.sleep(args.delay_seconds)

    with httpx.Client(timeout=args.timeout_seconds) as client:
        response = client.post(
            f"{args.server_url}/v1/location/SendInstruction",
            headers={"Content-Type": "application/json", "Accept": "text/plain"},
            json={"token": args.token, "jsonData": args.json_data},
        )
    return 0 if response.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
