#!/usr/bin/env python3
"""Entry point for ruisi-twinioc-opeationrule-skill skill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from operation_rule_recorder import (  # noqa: E402
    DEFAULT_LOG_FILE,
    DEFAULT_PENDING_FILE,
    clear_pending_confirmation,
    format_as_csv,
    get_pending_confirmation,
    match_temperature_rules,
    match_alarm_rules,
    handle_incoming_alarm,
    query_records,
    save_pending_confirmation,
    write_record,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operation rule recorder — write or query rule records.")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Write a new log record.")
    mode.add_argument("--query-log", action="store_true", help="Query log records.")
    mode.add_argument("--match-temperature", action="store_true", help="Match recorded temperature rules.")
    mode.add_argument("--match-alarm", action="store_true", help="Match recorded alarm rules.")
    mode.add_argument("--handle-alarm", action="store_true", help="Handle incoming alarm event and return latest related rule.")
    mode.add_argument("--save-pending", action="store_true", help="Save a pending confirmation action.")
    mode.add_argument("--get-pending", action="store_true", help="Get a pending confirmation action.")
    mode.add_argument("--clear-pending", action="store_true", help="Clear a pending confirmation action.")

    # write params
    parser.add_argument("--token", default=None, help="Scene token.")
    parser.add_argument(
        "--source",
        default=None,
        choices=["alarm", "temperature", "schedule"],
        help="Trigger source: alarm, temperature, or schedule.",
    )
    parser.add_argument("--query", dest="user_query", default=None, help="User input text.")
    parser.add_argument("--device-name", default=None, help="Current device or location name for temperature matching.")
    parser.add_argument("--temperature-value", type=float, default=None, help="Current temperature value for temperature matching.")
    parser.add_argument("--confirmation-text", default=None, help="Confirmation text for pending action storage.")
    parser.add_argument("--execute-query", default=None, help="Resolved command query for confirmed execution.")
    parser.add_argument("--matched-rule-json", default=None, help="Matched rule payload JSON for pending action storage.")

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
    parser.add_argument("--pending-file", default=None, help="Custom path to pending confirmation storage.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_file = Path(args.log_file) if args.log_file else DEFAULT_LOG_FILE
    pending_file = Path(args.pending_file) if args.pending_file else DEFAULT_PENDING_FILE

    if args.write:
        if not args.user_query:
            print(json.dumps({"success": False, "error": "--query is required for --write"}, ensure_ascii=False))
            return 1
        try:
            record = write_record(
                token=args.token,
                source=args.source or "alarm",
                query=args.user_query,
                log_file=log_file,
            )
            print(json.dumps({"success": True, "record": record}, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
            return 1

    if args.match_temperature:
        if args.temperature_value is None:
            print(json.dumps({"success": False, "error": "--temperature-value is required for --match-temperature"}, ensure_ascii=False))
            return 1
        if not args.device_name:
            print(json.dumps({"success": False, "error": "--device-name is required for --match-temperature"}, ensure_ascii=False))
            return 1

        matches = match_temperature_rules(
            temperature=args.temperature_value,
            device_name=args.device_name,
            token=args.token,
            log_file=log_file,
        )
        print(json.dumps({"total": len(matches), "matches": matches}, ensure_ascii=False, indent=2))
        return 0

    if args.match_alarm:
        if not args.device_name:
            print(json.dumps({"success": False, "error": "--device-name is required for --match-alarm"}, ensure_ascii=False))
            return 1

        matches = match_alarm_rules(
            device_name=args.device_name,
            token=args.token,
            log_file=log_file,
        )
        print(json.dumps({"total": len(matches), "matches": matches}, ensure_ascii=False, indent=2))
        return 0

    if args.handle_alarm:
        if not args.device_name:
            print(json.dumps({"success": False, "error": "--device-name is required for --handle-alarm"}, ensure_ascii=False))
            return 1

        result = handle_incoming_alarm(
            device_name=args.device_name,
            alarm_source=(args.source or "camera"),
            log_file=log_file,
        )
        if not result:
            print(json.dumps({"success": True, "match": None}, ensure_ascii=False, indent=2))
            return 0

        print(json.dumps({"success": True, "match": result}, ensure_ascii=False, indent=2))
        return 0

    if args.save_pending:
        if not args.token:
            print(json.dumps({"success": False, "error": "--token is required for --save-pending"}, ensure_ascii=False))
            return 1
        if not args.execute_query:
            print(json.dumps({"success": False, "error": "--execute-query is required for --save-pending"}, ensure_ascii=False))
            return 1

        matched_rule = None
        if args.matched_rule_json:
            try:
                matched_rule = json.loads(args.matched_rule_json)
            except json.JSONDecodeError as exc:
                print(json.dumps({"success": False, "error": f"--matched-rule-json JSON 解析失败: {exc}"}, ensure_ascii=False))
                return 1

        record = save_pending_confirmation(
            token=args.token,
            source=args.source or "temperature",
            confirmation_text=args.confirmation_text or "",
            execute_query=args.execute_query,
            matched_rule=matched_rule,
            pending_file=pending_file,
        )
        print(json.dumps({"success": True, "pending": record}, ensure_ascii=False, indent=2))
        return 0

    if args.get_pending:
        if not args.token:
            print(json.dumps({"success": False, "error": "--token is required for --get-pending"}, ensure_ascii=False))
            return 1
        pending = get_pending_confirmation(token=args.token, pending_file=pending_file)
        print(json.dumps({"success": True, "pending": pending}, ensure_ascii=False, indent=2))
        return 0

    if args.clear_pending:
        if not args.token:
            print(json.dumps({"success": False, "error": "--token is required for --clear-pending"}, ensure_ascii=False))
            return 1
        cleared = clear_pending_confirmation(token=args.token, pending_file=pending_file)
        print(json.dumps({"success": True, "cleared": cleared}, ensure_ascii=False, indent=2))
        return 0

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
