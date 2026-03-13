#!/usr/bin/env python3
"""Standalone entry for temperature-sensor-instruction skill."""

from __future__ import annotations

import argparse
import sys

from temperature_checker import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_INTERVAL,
    TARGET_LEDGER_ID,
    check_and_send,
)


TOKEN_ENV_VAR = "gj6mxa"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check temperature and send instruction when above threshold.")
    parser.add_argument(
        "--token",
        default=None,
        help=f"Token for SendInstruction (default: {TOKEN_ENV_VAR}).",
    )
    parser.add_argument("--base-url", default="http://test.twinioc.net/api/editor/v1", help="API base URL.")
    parser.add_argument("--location-id", default="dyo6vaow6203kx09", help="Location ID.")
    parser.add_argument(
        "--device-query",
        default=None,
        help="User input used to match device by 安装位置 or 孪生体实例名称.",
    )
    parser.add_argument(
        "--device-data-file",
        default=None,
        help="Path to data_organized.json for device matching.",
    )
    parser.add_argument(
        "--target-ledger-id",
        default=TARGET_LEDGER_ID,
        help=f"Fallback target user ledger ID when --device-query is missing (default: {TARGET_LEDGER_ID}).",
    )
    parser.add_argument("--start-time", default=None, help="Query start time (format: YYYY-MM-DD HH:MM:SS).")
    parser.add_argument("--end-time", default=None, help="Query end time (format: YYYY-MM-DD HH:MM:SS).")
    parser.add_argument("--timeout", type=float, default=100.0, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Maximum temperature query attempts (default: {DEFAULT_MAX_ATTEMPTS}).",
    )
    parser.add_argument(
        "--retry-interval",
        type=float,
        default=DEFAULT_RETRY_INTERVAL,
        help=f"Seconds to wait between retries (default: {DEFAULT_RETRY_INTERVAL}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="(disabled) Simulate sending instruction without actual API call.")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output.")

    args = parser.parse_args()

    token = args.token or TOKEN_ENV_VAR
    if not token:
        print("ERROR: No token provided. Set --token.", file=sys.stderr)
        return 1

    success, reply_message = check_and_send(
        token=token,
        base_url=args.base_url,
        location_id=args.location_id,
        target_ledger_id=args.target_ledger_id,
        device_query=args.device_query,
        device_data_file=args.device_data_file,
        start_time=args.start_time,
        end_time=args.end_time,
        timeout=args.timeout,
        max_attempts=args.max_attempts,
        retry_interval=args.retry_interval,
        verbose=not args.quiet,
    )

    if not args.quiet and reply_message:
        print(reply_message)

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
