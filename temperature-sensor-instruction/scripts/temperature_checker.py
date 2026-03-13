#!/usr/bin/env python3
"""Temperature sensor workflow for temperature-sensor-instruction skill."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://test.twinioc.net/api/editor/v1"
DEFAULT_LOCATION_ID = "dyo6vaow6203kx09"
TWIN_CATEGORY_CONFIG_ID = "hcwn2ha6p49661rm"
QUERY_LEVEL_ID = "gez4ermd715t31le"
TARGET_LEDGER_ID = "R3nazZz8Pyb6o7uc"
# TRIGGER_THRESHOLD = 20.0  # disabled: threshold judgment moved to AI
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_INTERVAL = 1.0
DEFAULT_DEVICE_DATA_FILE = Path(__file__).resolve().parent.parent / "data_organized.json"
# INSTALL_LOCATION_PLACEHOLDER = "__INSTALL_LOCATION__"  # disabled: SendInstruction disabled
# DEFAULT_SEND_INSTRUCTION_JSON = (
#     "B08：关闭灯：__INSTALL_LOCATION__照明灯开关$B09：打开温控器：__INSTALL_LOCATION__温控器"
#     "$&打开温控器：__INSTALL_LOCATION__温控器"
#     "$&根据最优策略，已经为您规划如下执行计划：\n"
#     "1、关闭灯：__INSTALL_LOCATION__照明灯开关\n"
#     "2、打开温控器：__INSTALL_LOCATION__温控器"
# )
# HOT_REPLY_TEMPLATE = "{device}当前温度{temperature}℃，稍微有点热，为您打开{device}温控器，另外，照明灯已帮您关闭。"
# NORMAL_REPLY_TEMPLATE = "{device}当前温度{temperature}℃，温度适宜，不需要开温控器"
FAILURE_REPLY_TEMPLATE = "温度查询失败，请稍后重试。"
DEVICE_NOT_FOUND_REPLY = "设备不存在。"
LOCATION_NO_DEVICE_REPLY = "当前位置没有设备。"
AMBIGUOUS_DEVICE_REPLY = "当前位置存在多个设备，请提供更具体的孪生体实例名称。"

QUERY_DIMENSION_NAMES = (
    "时间",
    "用户台账ID",
    "温度",
    "湿度",
    "电池电量",
    "区域",
)


@dataclass(frozen=True)
class ResolvedDevice:
    ledger_id: str
    install_location: str
    twin_name: str

    @property
    def display_name(self) -> str:
        return self.install_location or self.twin_name or self.ledger_id


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_dimensions() -> list[dict[str, str]]:
    return [{"columnName": name} for name in QUERY_DIMENSION_NAMES]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def contains_with_numeric_boundary(text: str, needle: str) -> bool:
    if not text or not needle:
        return False

    start = text.find(needle)
    while start != -1:
        end = start + len(needle)
        if needle[-1].isdigit() and end < len(text) and text[end].isdigit():
            start = text.find(needle, start + 1)
            continue
        if needle[0].isdigit() and start > 0 and text[start - 1].isdigit():
            start = text.find(needle, start + 1)
            continue
        return True

    return False


def looks_like_location_input(user_input: str) -> bool:
    hints = ("位置", "区域", "大厅", "会议室", "机房", "侧", "层", "东", "西", "南", "北")
    return any(hint in user_input for hint in hints)


def load_device_catalog(device_data_file: Path = DEFAULT_DEVICE_DATA_FILE) -> dict[str, dict[str, str]]:
    with device_data_file.open("r", encoding="utf-8") as f:
        parsed = json.load(f)

    if not isinstance(parsed, dict):
        raise ValueError("device catalog root must be an object")

    catalog: dict[str, dict[str, str]] = {}
    for ledger_id, meta in parsed.items():
        if not isinstance(ledger_id, str) or not isinstance(meta, dict):
            continue
        install_location = str(meta.get("安装位置", "")).strip()
        twin_name = str(meta.get("孪生体实例名称", "")).strip()
        catalog[ledger_id] = {
            "安装位置": install_location,
            "孪生体实例名称": twin_name,
        }
    return catalog


def resolve_device(
    user_input: str | None,
    fallback_ledger_id: str,
    device_data_file: Path = DEFAULT_DEVICE_DATA_FILE,
) -> tuple[ResolvedDevice | None, str | None]:
    try:
        catalog = load_device_catalog(device_data_file)
    except Exception:
        return None, FAILURE_REPLY_TEMPLATE

    if not user_input or not user_input.strip():
        fallback_meta = catalog.get(fallback_ledger_id, {})
        return (
            ResolvedDevice(
                ledger_id=fallback_ledger_id,
                install_location=str(fallback_meta.get("安装位置", "")).strip(),
                twin_name=str(fallback_meta.get("孪生体实例名称", "")).strip(),
            ),
            None,
        )

    query_raw = user_input.strip()
    query_norm = normalize_text(query_raw)
    if not query_norm:
        return None, DEVICE_NOT_FOUND_REPLY

    # Support direct user ledger ID input.
    for ledger_id in catalog:
        if normalize_text(ledger_id) == query_norm:
            meta = catalog[ledger_id]
            return (
                ResolvedDevice(
                    ledger_id=ledger_id,
                    install_location=meta.get("安装位置", "").strip(),
                    twin_name=meta.get("孪生体实例名称", "").strip(),
                ),
                None,
            )

    scored_matches: list[tuple[int, str]] = []
    for ledger_id, meta in catalog.items():
        location = meta.get("安装位置", "").strip()
        twin_name = meta.get("孪生体实例名称", "").strip()
        location_norm = normalize_text(location) if location else ""
        twin_norm = normalize_text(twin_name) if twin_name else ""
        score = -1

        if twin_norm and query_norm == twin_norm:
            score = 120
        elif location_norm and query_norm == location_norm:
            score = 110
        elif twin_norm and contains_with_numeric_boundary(query_norm, twin_norm):
            score = 100
        elif location_norm and location_norm in query_norm:
            score = 90
        elif twin_norm and query_norm in twin_norm:
            score = 80
        elif location_norm and query_norm in location_norm:
            score = 70

        if score >= 0:
            scored_matches.append((score, ledger_id))

    if not scored_matches:
        if looks_like_location_input(query_raw):
            return None, LOCATION_NO_DEVICE_REPLY
        return None, DEVICE_NOT_FOUND_REPLY

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    top_score = scored_matches[0][0]
    top_ledgers = [ledger_id for score, ledger_id in scored_matches if score == top_score]
    if len(top_ledgers) > 1:
        return None, AMBIGUOUS_DEVICE_REPLY

    selected_ledger_id = top_ledgers[0]
    selected_meta = catalog[selected_ledger_id]
    return (
        ResolvedDevice(
            ledger_id=selected_ledger_id,
            install_location=selected_meta.get("安装位置", "").strip(),
            twin_name=selected_meta.get("孪生体实例名称", "").strip(),
        ),
        None,
    )


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


def post_json(url: str, payload: dict[str, Any], timeout: float = 100.0) -> tuple[int, str, Any | None]:
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
    timeout: float = 100.0,
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
        payload = {
            "batchQueryDataRequest": [
                {
                    "twinCategoryConfigID": TWIN_CATEGORY_CONFIG_ID,
                    "queryTimeDataRequest": {
                        "isRealTime": True,
                        "dimensions": build_dimensions(),
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
                f"attempt={attempt_index + 1}/{total_attempts}",
                flush=True,
            )

        if attempt_index + 1 >= total_attempts:
            break

        if retry_delay > 0:
            time.sleep(retry_delay)

    return (False, None, last_message)


# def should_send_instruction(temperature: float, threshold: float = TRIGGER_THRESHOLD) -> bool:
#     return temperature > threshold


def format_temperature_for_reply(temperature: float) -> str:
    return str(temperature)


# def build_reply_message(
#     temperature: float,
#     device_name: str,
#     threshold: float = TRIGGER_THRESHOLD,
# ) -> str:
#     temperature_text = format_temperature_for_reply(temperature)
#     if should_send_instruction(temperature, threshold):
#         return HOT_REPLY_TEMPLATE.format(device=device_name, temperature=temperature_text)
#     return NORMAL_REPLY_TEMPLATE.format(device=device_name, temperature=temperature_text)


# def render_instruction_json(template: str, install_location: str) -> str:
#     location = install_location.strip()
#     if not location:
#         raise ValueError("install_location is empty")
#
#     if INSTALL_LOCATION_PLACEHOLDER in template:
#         return template.replace(INSTALL_LOCATION_PLACEHOLDER, location)
#
#     return template.replace("大会议室", location)


# def send_instruction(
#     token: str,
#     json_data: str = DEFAULT_SEND_INSTRUCTION_JSON,
#     base_url: str = DEFAULT_BASE_URL,
#     timeout: float = 100.0,
#     verbose: bool = False,
# ) -> tuple[bool, str]:
#     send_url = f"{base_url.rstrip('/')}/location/SendInstruction"
#     payload = {"token": token, "jsonData": json_data}
#
#     status, response_text, _ = post_json(send_url, payload, timeout)
#     ok = 200 <= status < 300
#     msg = f"status={status} ok={ok} body={response_text}"
#
#     if verbose:
#         print(f"[{utc_iso(datetime.now(timezone.utc))}] send_instruction {msg}", flush=True)
#
#     return (ok, msg)


def check_and_send(
    token: str,
    base_url: str = DEFAULT_BASE_URL,
    location_id: str = DEFAULT_LOCATION_ID,
    target_ledger_id: str = TARGET_LEDGER_ID,
    device_query: str | None = None,
    device_data_file: str | None = None,
    # threshold: float = TRIGGER_THRESHOLD,  # disabled: judgment moved to AI
    # json_data: str = DEFAULT_SEND_INSTRUCTION_JSON,  # disabled: SendInstruction disabled
    start_time: str | None = None,
    end_time: str | None = None,
    timeout: float = 100.0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_interval: float = DEFAULT_RETRY_INTERVAL,
    verbose: bool = True,
    # dry_run: bool = False,  # disabled: SendInstruction disabled
) -> tuple[bool, str]:
    resolved_device, resolve_error = resolve_device(
        user_input=device_query,
        fallback_ledger_id=target_ledger_id,
        device_data_file=Path(device_data_file) if device_data_file else DEFAULT_DEVICE_DATA_FILE,
    )
    if resolved_device is None:
        return False, resolve_error or DEVICE_NOT_FOUND_REPLY

    target_ledger_id = resolved_device.ledger_id
    device_name = resolved_device.display_name
    # instruction_location = (resolved_device.install_location or device_name).strip()  # disabled: only needed for SendInstruction
    # if not instruction_location:
    #     return False, DEVICE_NOT_FOUND_REPLY

    if verbose:
        print(
            f"[{utc_iso(datetime.now(timezone.utc))}] device "
            f"ledger_id={resolved_device.ledger_id} "
            f"location={resolved_device.install_location or '-'} "
            f"twin={resolved_device.twin_name or '-'}",
            flush=True,
        )

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

    reply_message = f"{device_name}当前温度{str(temperature)}℃"
    return True, reply_message

    # --- SendInstruction disabled: threshold/send logic moved to AI ---
    # reply_message = build_reply_message(temperature, device_name, threshold)
    #
    # if not should_send_instruction(temperature, threshold):
    #     if verbose:
    #         print(
    #             f"[{utc_iso(datetime.now(timezone.utc))}] temp <= {threshold}, skip SendInstruction",
    #             flush=True,
    #         )
    #     return True, reply_message
    #
    # try:
    #     rendered_json_data = render_instruction_json(json_data, instruction_location)
    # except Exception as exc:
    #     if verbose:
    #         print(
    #             f"[{utc_iso(datetime.now(timezone.utc))}] render_instruction_json failed: {exc}",
    #             flush=True,
    #         )
    #     return False, FAILURE_REPLY_TEMPLATE
    #
    # if dry_run:
    #     if verbose:
    #         print(
    #             f"[{utc_iso(datetime.now(timezone.utc))}] DRY_RUN: would send instruction for "
    #             f"temp={temperature} location={instruction_location} jsonData={rendered_json_data}",
    #             flush=True,
    #         )
    #     return True, reply_message
    #
    # ok, send_message = send_instruction(
    #     token=token,
    #     json_data=rendered_json_data,
    #     base_url=base_url,
    #     timeout=timeout,
    #     verbose=verbose,
    # )
    #
    # if not ok:
    #     return False, FAILURE_REPLY_TEMPLATE
    #
    # return True, reply_message
