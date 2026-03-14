#!/usr/bin/env python3
"""Entry point for operation-logger skill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from operation_logger import (  # noqa: E402
    DEFAULT_LOG_FILE,
    format_as_csv,
    query_records,
    write_record,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operation logger — write or query interaction history.")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Write a new log record.")
    mode.add_argument("--query-log", action="store_true", help="Query log records.")

    # write params
    parser.add_argument("--token", default=None, help="Scene token.")
    parser.add_argument(
        "--source",
        default=None,
        choices=["alarm", "temperature"],
        help="Trigger source: alarm or temperature.",
    )
    parser.add_argument("--query", dest="user_query", default=None, help="User input text.")
    parser.add_argument("--instruction", default="", help="AI-generated Chinese execution plan (plan_text).")

    # query params
    parser.add_argument("--date", default=None, help="Filter by date YYYY-MM-DD.")
    parser.add_argument("--last", type=int, default=20, help="Return last N records (default: 20).")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["json", "csv"],
        default="json",
        help="Output format for --query-log. Default: json.",
    )

    parser.add_argument("--log-file", default=None, help="Custom path to .jsonl log file.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_file = Path(args.log_file) if args.log_file else DEFAULT_LOG_FILE

    if args.write:
        if not args.token:
            print(json.dumps({"success": False, "error": "--token is required for --write"}, ensure_ascii=False))
            return 1
        if not args.user_query:
            print(json.dumps({"success": False, "error": "--query is required for --write"}, ensure_ascii=False))
            return 1
        try:
            record = write_record(
                token=args.token,
                source=args.source or "alarm",
                query=args.user_query,
                instruction=args.instruction,
                log_file=log_file,
            )
            print(json.dumps({"success": True, "record": record}, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
            return 1

    # --query-log
    records = query_records(
        token=args.token,
        source=args.source,
        date=args.date,
        last=args.last,
        log_file=log_file,
    )

    if args.output_format == "csv":
        print(format_as_csv(records))
    else:
        print(json.dumps({"total": len(records), "records": records}, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
