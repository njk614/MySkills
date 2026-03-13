#!/usr/bin/env python3
"""Run one alarm polling cycle and send two instructions when alarms are found."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://test.twinioc.net/api/editor/v1"
DEFAULT_LOCATION_ID = "dyo6vaow6203kx09"
DEFAULT_LEVEL_IDS = ["gez4ermd715t31le"]
TOKEN_ENV_VAR = "gj6mxa"
DEFAULT_JSON_DATA_1 = (
    "B08：关闭灯：大会议室照明灯开关$B01：聚焦对象：大会议室摄像头1"
    "$&产生新告警1$&根据最优策略，已经为您规划如下执行计划：\n"
    "1、关闭灯：大会议室照明灯开关\n"
    "2、聚焦对象：大会议室摄像头1"
)

DEFAULT_JSON_DATA_2 = (
    "E02：筛选：设置显示模式，3×3"
    "$&产生新告警1$&根据最优策略，已经为您规划如下执行计划：\n"
    "1、筛选：设置显示模式，3×3"
)
NO_ALARM_TEXT = {"", "null", "[]", "{}", "\"\""}
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
NO_ALARM_SIGNATURE = "__NO_ALARM__"
DEFAULT_STATE_FILENAME = ".alarm_poller_state.json"


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def api_time(dt: datetime) -> str:
    return dt.strftime(TIME_FORMAT)


def parse_api_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, TIME_FORMAT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid time '{value}', expected format: {TIME_FORMAT}") from exc
    return api_time(parsed)


def split_level_ids(raw_values: list[str]) -> list[str]:
    level_ids: list[str] = []
    for raw in raw_values:
        parts = [part.strip() for part in raw.split(",")]
        level_ids.extend([part for part in parts if part])
    if not level_ids:
        raise ValueError("At least one level ID is required.")
    return level_ids


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, str, Any | None]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        method="POST",
        headers={"accept": "text/plain", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            response_text = response.read().decode("utf-8", errors="replace").strip()
    except error.HTTPError as exc:
        status = exc.code
        response_text = exc.read().decode("utf-8", errors="replace").strip()
    except error.URLError as exc:
        return 0, f"URLError: {exc}", None

    try:
        parsed = json.loads(response_text) if response_text else None
    except json.JSONDecodeError:
        parsed = None
    return status, response_text, parsed


def has_alarm_data(parsed: Any | None, response_text: str) -> bool:
    if parsed is None:
        return response_text.strip().lower() not in NO_ALARM_TEXT
    return _contains_alarm(parsed)


def _contains_alarm(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        for key in ("alarmData", "alarms", "alarmList", "items", "records", "rows", "data", "result"):
            if key in value and _contains_alarm(value[key]):
                return True
        for key in ("total", "count", "size", "alarmCount", "recordCount"):
            count = value.get(key)
            if isinstance(count, (int, float)) and count > 0:
                return True
        for nested in value.values():
            if isinstance(nested, (list, dict)) and _contains_alarm(nested):
                return True
        return False
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one alarm poll request and send two SendInstruction commands when alarms are found."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL.")
    parser.add_argument("--location-id", default=DEFAULT_LOCATION_ID, help="Location ID for alarm polling.")
    parser.add_argument(
        "--level-ids",
        nargs="+",
        default=DEFAULT_LEVEL_IDS,
        help="One or multiple level IDs. Supports comma-separated input.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help=f"Token used by SendInstruction. Default: {TOKEN_ENV_VAR}.",
    )
    parser.add_argument("--json-data-1", default=DEFAULT_JSON_DATA_1, help="First instruction jsonData.")
    parser.add_argument("--json-data-2", default=DEFAULT_JSON_DATA_2, help="Second instruction jsonData.")
    parser.add_argument(
        "--begin-generation-time", type=parse_api_time, default=None, help="Format: YYYY-MM-DD HH:MM:SS"
    )
    parser.add_argument(
        "--end-generation-time", type=parse_api_time, default=None, help="Format: YYYY-MM-DD HH:MM:SS"
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help=f"Path to dedupe state file (default: sibling {DEFAULT_STATE_FILENAME}).",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    parser.add_argument("--verbose", action="store_true", help="Print no-alarm logs.")
    args = parser.parse_args()
    args.level_ids = split_level_ids(args.level_ids)
    return args


def resolve_token(args: argparse.Namespace) -> str:
    token = args.token or TOKEN_ENV_VAR
    if not token:
        print("token is required. Use --token.", file=sys.stderr)
        raise SystemExit(2)
    return token


def resolve_time_window(args: argparse.Namespace) -> tuple[str, str]:
    now_text = api_time(datetime.now())
    begin_time = args.begin_generation_time or now_text
    end_time = args.end_generation_time or now_text
    return begin_time, end_time


def resolve_state_file(args: argparse.Namespace) -> Path:
    if args.state_file:
        return Path(args.state_file).expanduser().resolve()
    return (Path(__file__).resolve().parent / DEFAULT_STATE_FILENAME).resolve()


def load_last_alarm_signature(state_file: Path) -> str | None:
    if not state_file.exists():
        return None
    try:
        content = state_file.read_text(encoding="utf-8")
        payload = json.loads(content)
    except (OSError, json.JSONDecodeError):
        return None
    signature = payload.get("last_batch_alarm_signature")
    return signature if isinstance(signature, str) and signature else None


def save_last_alarm_signature(state_file: Path, signature: str) -> None:
    payload = {
        "last_batch_alarm_signature": signature,
        "updatedAt": utc_iso(datetime.now(timezone.utc)),
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = state_file.with_name(f"{state_file.name}.tmp")
    tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file.replace(state_file)


def build_alarm_signature(alarm_snapshots: list[dict[str, Any]]) -> str:
    canonical = json.dumps(alarm_snapshots, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_once(args: argparse.Namespace) -> int:
    alarm_url = f"{args.base_url.rstrip('/')}/public/location/{args.location_id}/batchAlarmData"
    send_url = f"{args.base_url.rstrip('/')}/location/SendInstruction"
    token = resolve_token(args)
    begin_time, end_time = resolve_time_window(args)
    state_file = resolve_state_file(args)
    last_signature = load_last_alarm_signature(state_file)
    matched_levels: list[str] = []
    alarm_snapshots: list[dict[str, Any]] = []
    all_batch_queries_ok = True

    for level_id in args.level_ids:
        query_payload = {
            "beginGenerationTime": begin_time,
            "endGenerationTime": end_time,
            "levelID": level_id,
            "isRealTime": True,
        }
        status, response_text, parsed = post_json(alarm_url, query_payload, timeout=args.timeout)
        if status == 0:
            all_batch_queries_ok = False
            print(f"[{utc_iso(datetime.now(timezone.utc))}] query failed level={level_id}: {response_text}", flush=True)
            continue
        if not 200 <= status < 300:
            all_batch_queries_ok = False
            print(
                f"[{utc_iso(datetime.now(timezone.utc))}] query http_error level={level_id} status={status} body={response_text}",
                flush=True,
            )
            continue

        if has_alarm_data(parsed, response_text):
            matched_levels.append(level_id)
            alarm_snapshots.append({
                "levelID": level_id,
                "response": parsed if parsed is not None else response_text,
            })
            print(f"[{utc_iso(datetime.now(timezone.utc))}] alarm found level={level_id}", flush=True)
        elif args.verbose:
            print(f"[{utc_iso(datetime.now(timezone.utc))}] no alarm level={level_id}", flush=True)

    alarm_flow_exit_code = 0
    current_signature: str | None = None
    should_persist_signature = False
    if not matched_levels:
        print(f"[{utc_iso(datetime.now(timezone.utc))}] no alarms found, skip SendInstruction", flush=True)
        if all_batch_queries_ok:
            current_signature = NO_ALARM_SIGNATURE
            should_persist_signature = True
    else:
        current_signature = build_alarm_signature(alarm_snapshots)
        matched_levels_text = ",".join(matched_levels)

        if all_batch_queries_ok and current_signature == last_signature:
            print(
                f"[{utc_iso(datetime.now(timezone.utc))}] alarm data unchanged, skip SendInstruction "
                f"matched_levels={matched_levels_text}",
                flush=True,
            )
        else:
            payloads = [
                {"token": token, "jsonData": args.json_data_1},
                {"token": token, "jsonData": args.json_data_2},
            ]
            all_send_ok = True
            for idx, payload in enumerate(payloads, start=1):
                status, response_text, _ = post_json(send_url, payload, timeout=args.timeout)
                ok = 200 <= status < 300
                all_send_ok = all_send_ok and ok
                print(
                    f"[{utc_iso(datetime.now(timezone.utc))}] send={idx}/2 matched_levels={matched_levels_text} "
                    f"status={status} ok={ok} body={response_text}",
                    flush=True,
                )

            alarm_flow_exit_code = 0 if all_send_ok else 1
            should_persist_signature = all_send_ok

    if (
        all_batch_queries_ok
        and should_persist_signature
        and current_signature is not None
        and current_signature != last_signature
    ):
        try:
            save_last_alarm_signature(state_file, current_signature)
        except OSError as exc:
            print(f"[{utc_iso(datetime.now(timezone.utc))}] state save failed: {exc}", flush=True)

    return alarm_flow_exit_code


def main() -> int:
    args = parse_args()
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
