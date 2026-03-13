#!/usr/bin/env python3
"""Standalone entry for temperature-sensor-instruction skill."""

from __future__ import annotations

import argparse
import sys

from temperature_checker import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_INTERVAL,
    TARGET_LEDGER_ID,
    TRIGGER_THRESHOLD,
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
        "--target-ledger-id",
        default=TARGET_LEDGER_ID,
        help=f"Target user ledger ID (default: {TARGET_LEDGER_ID}).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=TRIGGER_THRESHOLD,
        help=f"Temperature threshold (default: {TRIGGER_THRESHOLD}).",
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
    parser.add_argument("--dry-run", action="store_true", help="Simulate sending instruction without actual API call.")
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
        threshold=args.threshold,
        start_time=args.start_time,
        end_time=args.end_time,
        timeout=args.timeout,
        max_attempts=args.max_attempts,
        retry_interval=args.retry_interval,
        verbose=not args.quiet,
        dry_run=args.dry_run,
    )

    if not args.quiet and reply_message:
        print(reply_message)

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
