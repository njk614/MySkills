#!/usr/bin/env python3
"""Temperature sensor workflow for temperature-sensor-instruction skill."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://test.twinioc.net/api/editor/v1"
DEFAULT_LOCATION_ID = "dyo6vaow6203kx09"
TWIN_CATEGORY_CONFIG_ID = "hcwn2ha6p49661rm"
QUERY_LEVEL_ID = "gez4ermd715t31le"
TARGET_LEDGER_ID = "R3nazZz8Pyb6o7uc"
TRIGGER_THRESHOLD = 20.0
DEFAULT_QUERY_LOOKBACK_SECONDS = 1
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_INTERVAL = 1.0
DEFAULT_SEND_INSTRUCTION_JSON = (
    "B08：关闭灯：大会议室照明灯开关$B09：关闭温控器：大会议室温控器"
    "$&打开温控器：大会议室温控器"
    "$&根据最优策略，已经为您规划如下执行计划：\n"
    "1、关闭灯：大会议室照明灯开关\n"
    "2、关闭温控器：大会议室温控器"
)
HOT_REPLY_TEMPLATE = "大会议室当前温度{temperature}℃，稍微有点热，为您打开大会议室温控器，另外，照明灯已帮您关闭。"
NORMAL_REPLY_TEMPLATE = "大会议室当前温度{temperature}℃，温度适宜，不需要开温控器"
FAILURE_REPLY_TEMPLATE = "温度查询失败，请稍后重试。"

QUERY_DIMENSION_NAMES = (
    "时间",
    "用户台账ID",
    "温度",
    "湿度",
    "电池电量",
    "区域",
)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def api_time(dt: datetime) -> str:
    return dt.strftime(TIME_FORMAT)


def build_dimensions() -> list[dict[str, str]]:
    return [{"columnName": name} for name in QUERY_DIMENSION_NAMES]


def resolve_query_window(
    start_time: str | None,
    end_time: str | None,
    attempt_index: int,
) -> tuple[str, str]:
    if start_time is not None and end_time is not None:
        return start_time, end_time

    now = datetime.now()
    end_value = end_time or api_time(now)
    lookback_seconds = DEFAULT_QUERY_LOOKBACK_SECONDS + attempt_index
    start_value = start_time or api_time(now - timedelta(seconds=lookback_seconds))
    return start_value, end_value


def extract_temperature(parsed: Any | None, target_ledger_id: str) -> float | None:
    if not isinstance(parsed, dict):
        return None

    data_block = parsed.get("data")
    if not isinstance(data_block, dict):
        return None

    models = data_block.get("batchQueryDataModels")
    if not isinstance(models, list):
        return None

    for model in models:
        if not isinstance(model, dict):
            continue
        table_data = model.get("data")
        if not isinstance(table_data, list) or len(table_data) < 2:
            continue

        header = table_data[0]
        if not isinstance(header, list):
            continue

        try:
            ledger_index = header.index("用户台账ID")
            temperature_index = header.index("温度")
        except ValueError:
            continue

        for row in table_data[1:]:
            if not isinstance(row, list):
                continue
            if ledger_index >= len(row) or temperature_index >= len(row):
                continue
            if str(row[ledger_index]) != target_ledger_id:
                continue

            try:
                return float(row[temperature_index])
            except (TypeError, ValueError):
                return None

    return None


def post_json(url: str, payload: dict[str, Any], timeout: float = 10.0) -> tuple[int, str, Any | None]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        method="POST",
        headers={"accept": "text/plain", "Content-Type": "application/json"},
    )
    status = 0
    response_text = ""

    try:
        with request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            response_text = response.read().decode("utf-8", errors="replace").strip()
    except error.HTTPError as exc:
        status = exc.code
        try:
            response_text = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            response_text = str(exc)
    except Exception as exc:
        return (0, str(exc), None)

    try:
        parsed = json.loads(response_text) if response_text else None
    except json.JSONDecodeError:
        parsed = None
    return (status, response_text, parsed)


def query_temperature(
    base_url: str = DEFAULT_BASE_URL,
    location_id: str = DEFAULT_LOCATION_ID,
    target_ledger_id: str = TARGET_LEDGER_ID,
    start_time: str | None = None,
    end_time: str | None = None,
    timeout: float = 10.0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_interval: float = DEFAULT_RETRY_INTERVAL,
    verbose: bool = False,
) -> tuple[bool, float | None, str]:
    query_url = (
        f"{base_url.rstrip('/')}/public/location/{location_id}/"
        "twinTypeDistinguish/TwinTimeSeries/batchQueryData"
    )

    total_attempts = max(1, max_attempts)
    retry_delay = max(0.0, retry_interval)
    last_message = "query not executed"

    for attempt_index in range(total_attempts):
        attempt_start_time, attempt_end_time = resolve_query_window(start_time, end_time, attempt_index)
        payload = {
            "batchQueryDataRequest": [
                {
                    "twinCategoryConfigID": TWIN_CATEGORY_CONFIG_ID,
                    "queryTimeDataRequest": {
                        "isRealTime": True,
                        "dimensions": build_dimensions(),
                        "conditonTime": {
                            "startTime": attempt_start_time,
                            "endTime": attempt_end_time,
                        },
                    },
                }
            ],
            "levelID": QUERY_LEVEL_ID,
        }

        status, response_text, parsed = post_json(query_url, payload, timeout)

        if status == 0:
            last_message = f"query failed: {response_text}"
        elif not 200 <= status < 300:
            last_message = f"http_error status={status} body={response_text}"
        else:
            temperature_value = extract_temperature(parsed, target_ledger_id)
            if temperature_value is not None:
                msg = f"user_ledger_id={target_ledger_id} temperature={temperature_value}"
                if verbose:
                    print(f"[{utc_iso(datetime.now(timezone.utc))}] temp {msg}", flush=True)
                return (True, temperature_value, msg)
            last_message = f"not found user_ledger_id={target_ledger_id}"

        if verbose:
            print(
                f"[{utc_iso(datetime.now(timezone.utc))}] temp {last_message} "
                f"attempt={attempt_index + 1}/{total_attempts} "
                f"window=[{attempt_start_time}, {attempt_end_time}]",
                flush=True,
            )

        if attempt_index + 1 >= total_attempts:
            break

        if retry_delay > 0:
            time.sleep(retry_delay)

    return (False, None, last_message)


def should_send_instruction(temperature: float, threshold: float = TRIGGER_THRESHOLD) -> bool:
    return temperature > threshold


def format_temperature_for_reply(temperature: float) -> str:
    return str(int(round(temperature)))


def build_reply_message(temperature: float, threshold: float = TRIGGER_THRESHOLD) -> str:
    temperature_text = format_temperature_for_reply(temperature)
    if should_send_instruction(temperature, threshold):
        return HOT_REPLY_TEMPLATE.format(temperature=temperature_text)
    return NORMAL_REPLY_TEMPLATE.format(temperature=temperature_text)


def send_instruction(
    token: str,
    json_data: str = DEFAULT_SEND_INSTRUCTION_JSON,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 10.0,
    verbose: bool = False,
) -> tuple[bool, str]:
    send_url = f"{base_url.rstrip('/')}/location/SendInstruction"
    payload = {"token": token, "jsonData": json_data}

    status, response_text, _ = post_json(send_url, payload, timeout)
    ok = 200 <= status < 300
    msg = f"status={status} ok={ok} body={response_text}"

    if verbose:
        print(f"[{utc_iso(datetime.now(timezone.utc))}] send_instruction {msg}", flush=True)

    return (ok, msg)


def check_and_send(
    token: str,
    base_url: str = DEFAULT_BASE_URL,
    location_id: str = DEFAULT_LOCATION_ID,
    target_ledger_id: str = TARGET_LEDGER_ID,
    threshold: float = TRIGGER_THRESHOLD,
    json_data: str = DEFAULT_SEND_INSTRUCTION_JSON,
    start_time: str | None = None,
    end_time: str | None = None,
    timeout: float = 10.0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_interval: float = DEFAULT_RETRY_INTERVAL,
    verbose: bool = True,
    dry_run: bool = False,
) -> tuple[bool, str]:
    success, temperature, _ = query_temperature(
        base_url=base_url,
        location_id=location_id,
        target_ledger_id=target_ledger_id,
        start_time=start_time,
        end_time=end_time,
        timeout=timeout,
        max_attempts=max_attempts,
        retry_interval=retry_interval,
        verbose=verbose,
    )

    if not success:
        return False, FAILURE_REPLY_TEMPLATE

    reply_message = build_reply_message(temperature, threshold)

    if not should_send_instruction(temperature, threshold):
        if verbose:
            print(
                f"[{utc_iso(datetime.now(timezone.utc))}] temp <= {threshold}, skip SendInstruction",
                flush=True,
            )
        return True, reply_message

    if dry_run:
        if verbose:
            print(
                f"[{utc_iso(datetime.now(timezone.utc))}] DRY_RUN: would send instruction for temp={temperature}",
                flush=True,
            )
        return True, reply_message

    ok, send_message = send_instruction(
        token=token,
        json_data=json_data,
        base_url=base_url,
        timeout=timeout,
        verbose=verbose,
    )

    if not ok:
        return False, FAILURE_REPLY_TEMPLATE

    return True, reply_message
