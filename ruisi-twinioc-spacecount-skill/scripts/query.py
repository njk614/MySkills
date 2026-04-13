#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
COMMAND_SKILL_SCRIPTS = CURRENT_DIR.parent.parent / "ruisi-twinioc-command-skill" / "scripts"
if str(COMMAND_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMAND_SKILL_SCRIPTS))

from defaults import (
    DEFAULT_BASE_URL,
    DEFAULT_CREATED_TIME,
    DEFAULT_GRANULARITY,
    DEFAULT_LEVEL_NAME,
    DEFAULT_REGION_NAME,
    DEFAULT_RESERVATION_SPACE_TYPE,
    DEFAULT_SPACE_ID,
    DEFAULT_SPACE_NAME,
)
from skill_runtime import SkillRuntimeError, call_mcp_tool  # noqa: E402

SUPPORTED_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "get_reservable_spaces",
        "check_space_availability",
        "get_space_reservation_status",
        "create_space_reservation",
        "reschedule_space_reservation",
        "cancel_space_reservation",
        "get_space_utilization_index_data",
    }
)

PARAM_KEY_ALIASES: dict[str, str] = {
    "spacetype": "spaceType",
    "空间类型": "spaceType",
    "spacename": "spaceName",
    "空间名称": "spaceName",
    "spaceid": "spaceId",
    "空间id": "spaceId",
    "bookingstarttime": "startTime",
    "预定开始时间": "startTime",
    "bookingendtime": "endTime",
    "预定结束时间": "endTime",
    "bookingstatus": "bookingStatus",
    "预定状态": "bookingStatus",
    "bookingpersonid": "bookingPersonId",
    "预定人id": "bookingPersonId",
    "conflictflag": "conflictFlag",
    "冲突标识": "conflictFlag",
    "conflictresolutiontime": "conflictResolutionTime",
    "冲突解决时间": "conflictResolutionTime",
    "occupancystatus": "occupancyStatus",
    "占用状态": "occupancyStatus",
    "belongareaname": "regionName",
    "区域名称": "regionName",
    "onlinestatus": "onlineStatus",
    "在线状态": "onlineStatus",
    "spacestaus": "spaceStatus",
    "spacestatus": "spaceStatus",
    "空间状态": "spaceStatus",
    "twininstancename": "spaceName",
    "孪生体实例名称": "spaceName",
}

RESERVATION_QUERY_TOOLS: frozenset[str] = frozenset(
    {
        "get_reservable_spaces",
        "check_space_availability",
        "get_space_reservation_status",
    }
)

RESERVABLE_SPACE_TYPES: frozenset[str] = frozenset({"会议室", "灵活工位"})

GRANULARITY_ALIASES: dict[str, str] = {
    "hour": "Hour",
    "hours": "Hour",
    "hourly": "Hour",
    "小时": "Hour",
    "时": "Hour",
    "day": "Day",
    "days": "Day",
    "daily": "Day",
    "日": "Day",
    "天": "Day",
    "week": "Week",
    "weeks": "Week",
    "weekly": "Week",
    "周": "Week",
    "month": "Month",
    "months": "Month",
    "monthly": "Month",
    "月": "Month",
}

SPACE_TYPE_ALIASES: dict[str, str] = {
    "会议室": "会议室",
    "会议": "会议室",
    "meetingroom": "会议室",
    "meeting room": "会议室",
    "room": "会议室",
    "灵活工位": "灵活工位",
    "固定工位": "固定工位",
    "工位": "灵活工位",
    "desk": "灵活工位",
    "desks": "灵活工位",
    "hotdesk": "灵活工位",
    "hot desk": "灵活工位",
    "flexibledesk": "灵活工位",
    "flexible desk": "灵活工位",
    "flexibleworkstation": "灵活工位",
    "flexible workstation": "灵活工位",
    "fixedworkstation": "固定工位",
    "fixed workstation": "固定工位",
}

SPACE_TYPE_LOCALE_VALUES: dict[str, dict[str, str]] = {
    "会议室": {"zh-CN": "会议室", "en-US": "MeetingRoom"},
    "灵活工位": {"zh-CN": "灵活工位", "en-US": "FlexibleWorkstation"},
    "固定工位": {"zh-CN": "固定工位", "en-US": "FixedWorkstation"},
}

EN_VALUE_ALIASES: dict[str, str] = {
    "灵活工位": "FlexibleWorkstation",
    "固定工位": "FixedWorkstation",
    "flexibleworkstation": "FlexibleWorkstation",
    "flexible workstation": "FlexibleWorkstation",
    "fixedworkstation": "FixedWorkstation",
    "fixed workstation": "FixedWorkstation",
    "会议室": "MeetingRoom",
    "meetingroom": "MeetingRoom",
    "meeting room": "MeetingRoom",
    "空间预定记录": "SpaceReservationRecord",
    "spacereservationrecord": "SpaceReservationRecord",
    "机房": "Cabinet",
    "cabinet": "Cabinet",
    "已预定": "Booked",
    "booked": "Booked",
    "已取消": "Canceled",
    "canceled": "Canceled",
    "cancelled": "Canceled",
}


def _parse_json_arg(value: str) -> dict[str, Any]:
    parsed = json.loads(value or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("--mcp-args 必须是 JSON 对象")
    return parsed


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _normalize_alias_token(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", _string_value(value)).lower()


def _canonicalize_mcp_arg_keys(mcp_args: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in mcp_args.items():
        alias_key = _normalize_alias_token(key)
        canonical_key = PARAM_KEY_ALIASES.get(alias_key) or PARAM_KEY_ALIASES.get(_string_value(key)) or key
        normalized[canonical_key] = value
    return normalized


def _localize_general_value(value: Any, locale: str) -> Any:
    if locale != "en-US" or not isinstance(value, str):
        return value
    mapped = EN_VALUE_ALIASES.get(_normalize_alias_token(value)) or EN_VALUE_ALIASES.get(_string_value(value))
    return mapped or value


def _localize_general_mcp_args(mcp_args: dict[str, Any], locale: str) -> dict[str, Any]:
    if locale != "en-US":
        return dict(mcp_args)
    localized: dict[str, Any] = {}
    for key, value in mcp_args.items():
        if isinstance(value, list):
            localized[key] = [_localize_general_value(item, locale) for item in value]
            continue
        localized[key] = _localize_general_value(value, locale)
    return localized


def _normalize_locale(locale: str | None, payload: dict[str, Any] | None = None) -> str:
    raw = _string_value(locale).lower()
    if raw in {"en", "en-us", "english"}:
        return "en-US"
    if raw in {"zh", "zh-cn", "cn", "chinese"}:
        return "zh-CN"

    values = " ".join(
        _string_value(value)
        for value in (payload or {}).values()
        if isinstance(value, (str, int, float))
    )
    if re.search(r"[A-Za-z]", values) and not re.search(r"[\u4e00-\u9fff]", values):
        return "en-US"
    return "zh-CN"


def _has_value(payload: dict[str, Any], key: str) -> bool:
    return bool(_string_value(payload.get(key)))


def _set_default(payload: dict[str, Any], key: str, value: Any) -> None:
    if not _has_value(payload, key):
        payload[key] = value


def _format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _current_time_context() -> tuple[str, str, str]:
    now = datetime.now().replace(microsecond=0)
    hour_start = now.replace(minute=0, second=0)
    hour_end = now.replace(minute=59, second=59)
    return _format_dt(now), _format_dt(hour_start), _format_dt(hour_end)


def _normalize_granularity(value: Any) -> str:
    raw = _string_value(value)
    if not raw:
        return DEFAULT_GRANULARITY
    normalized = GRANULARITY_ALIASES.get(raw.lower())
    if normalized:
        return normalized
    compact = raw.replace(" ", "")
    normalized = GRANULARITY_ALIASES.get(compact.lower())
    if normalized:
        return normalized
    return raw


def _normalize_space_type(value: Any) -> str:
    raw = _string_value(value)
    if not raw:
        return ""
    normalized = SPACE_TYPE_ALIASES.get(raw.lower())
    if normalized:
        return normalized
    compact = raw.replace(" ", "")
    normalized = SPACE_TYPE_ALIASES.get(compact.lower())
    if normalized:
        return normalized
    return raw


def _localize_space_type(value: Any, locale: str) -> str:
    canonical = _normalize_space_type(value)
    if not canonical:
        return ""
    localized = SPACE_TYPE_LOCALE_VALUES.get(canonical, {})
    return localized.get(locale) or canonical


def _infer_space_type_from_name(value: Any) -> str:
    raw = _string_value(value)
    if not raw:
        return ""
    lowered = raw.lower()
    if "会议室" in raw or "meeting room" in lowered or lowered.endswith("room"):
        return "会议室"
    if "固定工位" in raw or "fixed workstation" in lowered:
        return "固定工位"
    if "灵活工位" in raw or "工位" in raw or "flexible workstation" in lowered or "desk" in lowered:
        return "灵活工位"
    return ""


def _normalize_reservation_identity(mcp_args: dict[str, Any], locale: str) -> None:
    if _has_value(mcp_args, "spaceType"):
        mcp_args["spaceType"] = _localize_space_type(mcp_args.get("spaceType"), locale)
        return

    inferred_space_type = _infer_space_type_from_name(mcp_args.get("spaceName"))
    if inferred_space_type:
        mcp_args["spaceType"] = _localize_space_type(inferred_space_type, locale)
        return

    mcp_args["spaceType"] = _localize_space_type(DEFAULT_RESERVATION_SPACE_TYPE, locale)


def _maybe_normalize_reservation_identity(tool_name: str, mcp_args: dict[str, Any], locale: str) -> None:
    if tool_name not in {"get_reservable_spaces", "check_space_availability", "get_space_reservation_status", "create_space_reservation"}:
        return
    _normalize_reservation_identity(mcp_args, locale)


def _normalize_level_name(value: Any) -> str:
    raw = _string_value(value)
    if not raw:
        return ""

    zh_match = re.fullmatch(r"楼层\s*(\d+)", raw, flags=re.IGNORECASE)
    if zh_match:
        return f"楼层{zh_match.group(1)}"

    en_match = re.fullmatch(r"floor\s*(\d+)", raw, flags=re.IGNORECASE)
    if en_match:
        return f"楼层{en_match.group(1)}"

    return raw


def _localize_level_name(value: Any, locale: str) -> str:
    normalized = _normalize_level_name(value)
    if not normalized:
        return ""

    match = re.fullmatch(r"楼层(\d+)", normalized)
    if not match:
        return normalized

    floor_number = match.group(1)
    if locale == "en-US":
        return f"Floor{floor_number}"
    return f"楼层{floor_number}"


def _apply_space_utilization_defaults(mcp_args: dict[str, Any], locale: str) -> dict[str, Any]:
    enriched = dict(mcp_args)
    now_text, hour_start_text, _hour_end_text = _current_time_context()
    _set_default(enriched, "levelName", _localize_level_name(DEFAULT_LEVEL_NAME, locale))
    if _has_value(enriched, "levelName"):
        enriched["levelName"] = _localize_level_name(enriched.get("levelName"), locale)
    enriched["granularity"] = _normalize_granularity(enriched.get("granularity"))
    _set_default(enriched, "startTime", hour_start_text)
    _set_default(enriched, "endTime", now_text)
    if "regionName" not in enriched or enriched.get("regionName") is None:
        enriched["regionName"] = DEFAULT_REGION_NAME
    return enriched


def _apply_reservation_query_defaults(tool_name: str, mcp_args: dict[str, Any], locale: str) -> dict[str, Any]:
    enriched = dict(mcp_args)
    now_text, _hour_start_text, hour_end_text = _current_time_context()
    _maybe_normalize_reservation_identity(tool_name, enriched, locale)

    if tool_name == "get_reservable_spaces":
        _set_default(enriched, "spaceType", _localize_space_type(DEFAULT_RESERVATION_SPACE_TYPE, locale))
        _set_default(enriched, "levelName", _localize_level_name(DEFAULT_LEVEL_NAME, locale))
        if _has_value(enriched, "levelName"):
            enriched["levelName"] = _localize_level_name(enriched.get("levelName"), locale)
        if "regionName" not in enriched or enriched.get("regionName") is None:
            enriched["regionName"] = DEFAULT_REGION_NAME
        _set_default(enriched, "startTime", now_text)
        _set_default(enriched, "endTime", hour_end_text)
        return enriched

    if tool_name == "check_space_availability":
        _set_default(enriched, "spaceType", _localize_space_type(DEFAULT_RESERVATION_SPACE_TYPE, locale))
        _set_default(enriched, "spaceId", DEFAULT_SPACE_ID)
        _set_default(enriched, "spaceName", DEFAULT_SPACE_NAME)
        _set_default(enriched, "startTime", now_text)
        _set_default(enriched, "endTime", hour_end_text)
        return enriched

    if tool_name == "create_space_reservation":
        _set_default(enriched, "spaceType", _localize_space_type(DEFAULT_RESERVATION_SPACE_TYPE, locale))
        _set_default(enriched, "spaceId", DEFAULT_SPACE_ID)
        _set_default(enriched, "spaceName", DEFAULT_SPACE_NAME)
        _set_default(enriched, "startTime", now_text)
        _set_default(enriched, "endTime", hour_end_text)
        return enriched

    if tool_name == "get_space_reservation_status":
        _set_default(enriched, "spaceType", _localize_space_type(DEFAULT_RESERVATION_SPACE_TYPE, locale))
        _set_default(enriched, "spaceId", DEFAULT_SPACE_ID)
        _set_default(enriched, "spaceName", DEFAULT_SPACE_NAME)
        return enriched

    if tool_name == "reschedule_space_reservation":
        _set_default(enriched, "spaceId", DEFAULT_SPACE_ID)
        _set_default(enriched, "createdTime", DEFAULT_CREATED_TIME)
        _set_default(enriched, "newStartTime", now_text)
        _set_default(enriched, "newEndTime", hour_end_text)
        return enriched

    if tool_name == "cancel_space_reservation":
        _set_default(enriched, "spaceId", DEFAULT_SPACE_ID)
        _set_default(enriched, "createdTime", DEFAULT_CREATED_TIME)
        return enriched

    return enriched


def _normalize_mcp_args(tool_name: str, mcp_args: dict[str, Any], locale: str) -> dict[str, Any]:
    normalized_args = _canonicalize_mcp_arg_keys(mcp_args)
    normalized_args = _localize_general_mcp_args(normalized_args, locale)
    if tool_name == "get_space_utilization_index_data":
        return _apply_space_utilization_defaults(normalized_args, locale)
    if tool_name in {
        "get_reservable_spaces",
        "check_space_availability",
        "get_space_reservation_status",
        "create_space_reservation",
        "reschedule_space_reservation",
        "cancel_space_reservation",
    }:
        return _apply_reservation_query_defaults(tool_name, normalized_args, locale)
    return dict(normalized_args)


def _validate_mcp_args(tool_name: str, mcp_args: dict[str, Any], locale: str) -> str | None:
    _maybe_normalize_reservation_identity(tool_name, mcp_args, locale)

    if tool_name == "get_reservable_spaces":
        space_type = _normalize_space_type(mcp_args.get("spaceType"))
        if space_type not in RESERVABLE_SPACE_TYPES:
            return "get_reservable_spaces 的 spaceType 只能是 会议室 或 灵活工位"

        mcp_args["spaceType"] = _localize_space_type(space_type, locale)
        return None

    if tool_name == "check_space_availability":
        space_type = _normalize_space_type(mcp_args.get("spaceType"))
        if space_type not in RESERVABLE_SPACE_TYPES:
            return "check_space_availability 的 spaceType 只能是 会议室 或 灵活工位"
        mcp_args["spaceType"] = _localize_space_type(space_type, locale)
        return None

    if tool_name == "get_space_reservation_status":
        if _has_value(mcp_args, "spaceType"):
            space_type = _normalize_space_type(mcp_args.get("spaceType"))
            if space_type not in RESERVABLE_SPACE_TYPES:
                return "get_space_reservation_status 的 spaceType 只能是 会议室 或 灵活工位"
            mcp_args["spaceType"] = _localize_space_type(space_type, locale)
        return None

    if tool_name == "create_space_reservation":
        space_type = _normalize_space_type(mcp_args.get("spaceType"))
        if space_type not in RESERVABLE_SPACE_TYPES:
            return "create_space_reservation 的 spaceType 只能是 会议室 或 灵活工位"
        mcp_args["spaceType"] = _localize_space_type(space_type, locale)
        return None

    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ruisi Twinioc spacecount MCP query entry")
    parser.add_argument("--token", required=True, help="场景 token")
    parser.add_argument("--base-url", default=None, help=f"孪易服务基础地址，默认 {DEFAULT_BASE_URL}")
    parser.add_argument("--mcp-tool", required=True, help="MCP 工具名称")
    parser.add_argument("--mcp-args", default="{}", help="MCP 工具参数 JSON 字符串")
    parser.add_argument("--locale", default=None, help="可选语言标识，如 zh-CN 或 en-US")
    return parser


async def _run_async(args: argparse.Namespace) -> int:
    tool_name = str(args.mcp_tool or "").strip()
    if not tool_name:
        print(json.dumps({"success": False, "error": "--mcp-tool 不能为空"}, ensure_ascii=False, indent=2))
        return 1
    if tool_name not in SUPPORTED_MCP_TOOLS:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"不支持的 MCP 工具: {tool_name}",
                    "supported_tools": sorted(SUPPORTED_MCP_TOOLS),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    try:
        mcp_args = _parse_json_arg(args.mcp_args)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"success": False, "error": f"--mcp-args 解析失败: {exc}"}, ensure_ascii=False, indent=2))
        return 1

    locale = _normalize_locale(getattr(args, "locale", None), mcp_args)
    mcp_args = _normalize_mcp_args(tool_name, mcp_args, locale)

    if "token" not in mcp_args:
        mcp_args["token"] = args.token

    validation_error = _validate_mcp_args(tool_name, mcp_args, locale)
    if validation_error:
        print(json.dumps({"success": False, "error": validation_error}, ensure_ascii=False, indent=2))
        return 1

    try:
        result = await call_mcp_tool(args.token, tool_name, mcp_args, base_url=args.base_url)
    except SkillRuntimeError as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
