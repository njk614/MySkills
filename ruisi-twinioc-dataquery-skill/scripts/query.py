#!/usr/bin/env python3
"""Unified read-only data query entry for ruisi-twinioc-dataquery-skill skill.

Two query modes:
  temperature   Query temperature sensor for a device.
  mcp           Call an MCP tool and return the result as JSON.

Examples:
  python scripts/query.py temperature --token gj6mxa --device-query "大厅东侧"
  python scripts/query.py mcp --token gj6mxa --mcp-tool get_scene_info
  python scripts/query.py mcp --token gj6mxa --mcp-tool get_twin_category_data --mcp-args '{"twinCategoryName": "可控摄像头"}'
  python scripts/query.py mcp --token gj6mxa --mcp-tool get_bind_video_instance_names
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Skill root:  e:\AI\Skills\ruisi-twinioc-dataquery-skill\scripts\query.py  → parent.parent
SKILL_ROOT = Path(__file__).resolve().parent.parent

# Workspace root (parent of skill root)
SKILLS_ROOT = SKILL_ROOT.parent

# MCP 查询结果缓存文件（token 变化时全部清空）
CACHE_FILE = SKILL_ROOT / ".runtime" / "mcp_cache.json"
CACHE_SCHEMA_VERSION = 2

# 实时/动态数据类工具，跳过缓存
_NO_CACHE_TOOLS: frozenset[str] = frozenset(
    {
        "get_scene_context",  # 含会话历史，实时变化
        "get_scene_info",
        "get_twin_category_data",
        "get_twin_category",
        "get_bind_video_instance_names",
        "get_twin_realtime_time_series_data",
    }
)

_SUPPORTED_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "get_scene_info",
        "get_twin_category_data",
        "get_twin_category",
        "get_scene_context",
        "get_bind_video_instance_names",
        "get_twin_realtime_time_series_data",
    }
)

# ---------------------------------------------------------------------------
# 温度传感器查询（本地设备解析 + MCP 实时孪生体时序查询）
# ---------------------------------------------------------------------------

_DEFAULT_SERVICE_BASE_URL = os.getenv("TWINEASY_BASE_URL", "http://test.twinioc.net").rstrip("/")
_TEMPERATURE_MCP_TOOL = "get_twin_realtime_time_series_data"
_DEFAULT_TARGET_LEDGER_ID = "R3nazZz8Pyb6o7uc"
_DEFAULT_ENTITY_ALIAS_FILE = SKILL_ROOT / "entity_aliases.json"

_MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "failure_reply": "温度查询失败，请稍后重试。",
        "mcp_missing_data_reply": "温度查询失败：MCP 返回了消息“{message}”，但没有 Data。按接口文档这属于失败，请检查 MCP 工具实现或 twinId/twinName 参数。",
        "device_not_found": "设备不存在。",
        "location_no_device": "当前位置没有设备。",
        "ambiguous_device": "当前位置存在多个设备，请提供更具体的孪生体实例名称。",
        "catalog_missing": "设备别名台账文件不存在: {path}",
        "temperature_reply": "{device_name}当前温度{temperature}℃",
        "rule_reply_joiner": "。",
        "unsupported_tool": "不支持的 MCP 工具: {tool}",
        "invoke_missing": "invoke_skill.py 不存在: {path}",
        "mcp_args_invalid": "--mcp-args JSON 解析失败: {error}",
        "temperature_field_missing": "未从孪生体实时数据中找到温度字段。",
    },
    "en-US": {
        "failure_reply": "Temperature query failed. Please try again later.",
        "mcp_missing_data_reply": "Temperature query failed: MCP returned message \"{message}\" but no Data payload. Per the API contract this is a failure. Check the MCP tool implementation or the twinId/twinName arguments.",
        "device_not_found": "The device was not found.",
        "location_no_device": "No device was found for the requested location.",
        "ambiguous_device": "Multiple devices matched the request. Please provide a more specific device name.",
        "catalog_missing": "Device alias catalog file does not exist: {path}",
        "temperature_reply": "The current temperature in {device_name} is {temperature}°C",
        "rule_reply_joiner": ". ",
        "unsupported_tool": "Unsupported MCP tool: {tool}",
        "invoke_missing": "invoke_skill.py does not exist: {path}",
        "mcp_args_invalid": "Failed to parse --mcp-args JSON: {error}",
        "temperature_field_missing": "No temperature field was found in the twin realtime data.",
    },
}

_EN_OPERATOR_TEXT: dict[str, str] = {
    "gt": "above",
    "gte": "at or above",
    "lt": "below",
    "lte": "at or below",
    "eq": "equal to",
}

_ACTION_TRANSLATIONS: dict[str, str] = {
    "打开照明灯": "Turn on the lights",
    "关闭照明灯": "Turn off the lights",
    "打开灯": "Turn on the lights",
    "关闭灯": "Turn off the lights",
    "打开温控器": "Turn on the air conditioner",
    "关闭温控器": "Turn off the air conditioner",
    "场景复位": "Reset the scene",
}

_TEMPERATURE_FIELD_NAMES: tuple[str, ...] = ("温度", "temperature")


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s'\"`，,。.;;！？!?~～、:_-]+", "", value).lower()


def _normalize_base_url(base_url: str | None) -> str:
    normalized = str(base_url or _DEFAULT_SERVICE_BASE_URL).strip().rstrip("/")
    for suffix in ("/api/editor/v1", "/api/editor/mcp", "/api/editor"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.rstrip("/")


def _normalize_locale(locale: str | None, text: str | None = None) -> str:
    raw = str(locale or "").strip().lower()
    if raw in {"en", "en-us", "english"}:
        return "en-US"
    if raw in {"zh", "zh-cn", "cn", "chinese"}:
        return "zh-CN"
    if text and re.search(r"[A-Za-z]", text) and not re.search(r"[\u4e00-\u9fff]", text):
        return "en-US"
    return "zh-CN"


def _message(locale: str, key: str, **kwargs: Any) -> str:
    template = _MESSAGES.get(locale, _MESSAGES["zh-CN"]).get(key) or _MESSAGES["zh-CN"][key]
    return template.format(**kwargs)


def _load_entity_aliases(alias_file: Path) -> list[dict[str, Any]]:
    if not alias_file.exists():
        return []
    try:
        parsed = json.loads(alias_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [value for value in parsed.values() if isinstance(value, dict)]
    return []


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _get_locale_ledger_ids(entry: dict[str, Any], locale: str) -> list[str]:
    ledger_ids = entry.get("ledger_ids")
    if not isinstance(ledger_ids, dict):
        return []
    return _list_values(ledger_ids.get(locale))


def _pick_resolved_ledger_id(device_info: dict[str, Any], locale: str) -> str:
    locale_ledger_ids = _get_locale_ledger_ids(device_info, locale)
    if locale_ledger_ids:
        return locale_ledger_ids[0]
    return str(device_info.get("ledger_id") or "")


def _normalize_threshold_text(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _contains_with_numeric_boundary(text: str, needle: str) -> bool:
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


def _get_primary_ledger_id(entry: dict[str, Any]) -> str:
    for locale in ("zh-CN", "en-US"):
        ledger_ids = _get_locale_ledger_ids(entry, locale)
        if ledger_ids:
            return ledger_ids[0]
    return ""


def _load_device_catalog() -> dict[str, dict[str, str]]:
    alias_entries = _load_entity_aliases(_DEFAULT_ENTITY_ALIAS_FILE)
    catalog: dict[str, dict[str, str]] = {}
    for meta in alias_entries:
        if not isinstance(meta, dict):
            continue
        primary_ledger_id = _get_primary_ledger_id(meta)
        if not primary_ledger_id:
            continue
        canonical_name_zh = str(meta.get("canonical_name_zh") or "").strip()
        system_name = str(meta.get("system_name") or "").strip()
        display_name_en = str(meta.get("display_name_en") or system_name).strip()
        catalog[primary_ledger_id] = {
            "ledger_id": primary_ledger_id,
            "canonical_name_zh": canonical_name_zh,
            "安装位置": canonical_name_zh,
            "孪生体实例名称": system_name,
            "system_name": system_name,
            "display_name_en": display_name_en,
            "aliases_en": _list_values(meta.get("aliases_en")),
            "aliases_zh": _list_values(meta.get("aliases_zh")),
            "ledger_ids": {
                "zh-CN": _get_locale_ledger_ids(meta, "zh-CN"),
                "en-US": _get_locale_ledger_ids(meta, "en-US"),
            },
        }
    return catalog


def _get_match_name(device_info: dict[str, Any]) -> str:
    return str(
        device_info.get("canonical_name_zh")
        or device_info.get("安装位置")
        or device_info.get("孪生体实例名称")
        or device_info.get("system_name")
        or device_info.get("ledger_id")
        or ""
    )


def _get_display_device_name(device_info: dict[str, Any], locale: str) -> str:
    if locale == "en-US":
        return str(
            device_info.get("display_name_en")
            or device_info.get("system_name")
            or device_info.get("canonical_name_zh")
            or device_info.get("安装位置")
            or device_info.get("孪生体实例名称")
            or device_info.get("ledger_id")
            or ""
        )
    return str(
        device_info.get("canonical_name_zh")
        or device_info.get("安装位置")
        or device_info.get("system_name")
        or device_info.get("display_name_en")
        or device_info.get("孪生体实例名称")
        or device_info.get("ledger_id")
        or ""
    )


def _get_twin_id(device_info: dict[str, Any]) -> str:
    for key in ("twin_id", "TwinId", "孪生体实例ID", "孪生体实例Id", "ledger_id"):
        value = str(device_info.get(key) or "").strip()
        if value:
            return value
    return ""


def _get_twin_name(device_info: dict[str, Any]) -> str:
    return str(device_info.get("孪生体实例名称") or device_info.get("twin_name") or "").strip()


def _score_candidate(query_norm: str, candidate: str, exact_score: int, contains_score: int, prefix_score: int) -> int:
    candidate_norm = _normalize_text(candidate)
    if not candidate_norm:
        return -1
    if query_norm == candidate_norm:
        return exact_score
    if _contains_with_numeric_boundary(query_norm, candidate_norm):
        return contains_score
    if candidate_norm.startswith(query_norm) or query_norm.startswith(candidate_norm):
        return prefix_score
    return -1


def _translate_action_text(
    action_text: str,
    locale: str,
    display_device_name: str = "",
    matched_device_name: str = "",
) -> str:
    if locale != "en-US":
        return action_text

    normalized_action = str(action_text or "").strip()
    if not normalized_action:
        return normalized_action
    if normalized_action in _ACTION_TRANSLATIONS:
        return _ACTION_TRANSLATIONS[normalized_action]

    cleaned_action = normalized_action
    for candidate in (matched_device_name, display_device_name):
        candidate = str(candidate or "").strip()
        if candidate:
            cleaned_action = cleaned_action.replace(candidate, "")
    cleaned_action = cleaned_action.strip()

    if "场景复位" in normalized_action:
        return "Reset the scene"

    verb = ""
    if cleaned_action.startswith(("关闭", "关掉")):
        verb = "Turn off"
        cleaned_action = re.sub(r"^(关闭|关掉)", "", cleaned_action).strip()
    elif cleaned_action.startswith(("打开", "开启")):
        verb = "Turn on"
        cleaned_action = re.sub(r"^(打开|开启)", "", cleaned_action).strip()

    if any(keyword in cleaned_action for keyword in ("照明灯", "灯开关", "灯")):
        target = "the lights"
    elif "温控器" in cleaned_action:
        target = "the air conditioner"
    else:
        target = cleaned_action or normalized_action

    if target in {"the lights", "the air conditioner"} and display_device_name:
        target = f"{target} in {display_device_name}"

    if verb:
        return f"{verb} {target}".strip()
    return target


def _build_rule_confirmation_text(locale: str, device_name: str, temperature: float, parsed_rule: dict[str, Any]) -> str:
    if locale != "en-US":
        return str(parsed_rule.get("confirmation_text") or "").strip()

    threshold = float(parsed_rule.get("threshold") or 0)
    operator = str(parsed_rule.get("operator") or "")
    action_text = _translate_action_text(
        str(parsed_rule.get("action_text") or "").strip(),
        locale,
        display_device_name=device_name,
        matched_device_name=str(parsed_rule.get("device_name") or "").strip(),
    )
    operator_text = _EN_OPERATOR_TEXT.get(operator, "matching")
    threshold_text = _normalize_threshold_text(threshold)
    temperature_text = _normalize_threshold_text(temperature)
    return (
        f"The current temperature in {device_name} is {temperature_text}°C, "
        f"which is {operator_text} the configured threshold of {threshold_text}°C. "
        f"{action_text}. Please confirm whether to execute it."
    )


def _resolve_device(
    user_input: str | None,
    fallback_ledger_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """返回 (device_info, error_reply)。device_info 包含 ledger_id / install_location / twin_name。"""
    try:
        catalog = _load_device_catalog()
    except Exception:
        return None, "failure_reply"

    if not user_input or not user_input.strip():
        for lid, meta in catalog.items():
            all_ledger_ids: list[str] = []
            ledger_ids = meta.get("ledger_ids")
            if isinstance(ledger_ids, dict):
                for values in ledger_ids.values():
                    all_ledger_ids.extend(_list_values(values))
            if fallback_ledger_id == lid or fallback_ledger_id in all_ledger_ids:
                return {"ledger_id": lid,
                        "install_location": meta.get("安装位置", ""),
                        "twin_name": meta.get("孪生体实例名称", ""),
                        **meta}, None
        return None, "device_not_found"

    query_raw = user_input.strip()
    query_norm = _normalize_text(query_raw)
    if not query_norm:
        return None, "device_not_found"

    # 直接匹配 ledger_id
    for lid in catalog:
        if _normalize_text(lid) == query_norm:
            meta = catalog[lid]
            return {"ledger_id": lid,
                    "install_location": meta.get("安装位置", ""),
                    "twin_name": meta.get("孪生体实例名称", ""),
                    **meta}, None

        meta = catalog[lid]
        all_ledger_ids: list[str] = []
        ledger_ids = meta.get("ledger_ids")
        if isinstance(ledger_ids, dict):
            for values in ledger_ids.values():
                all_ledger_ids.extend(_list_values(values))
        if query_norm in {_normalize_text(candidate) for candidate in all_ledger_ids if candidate}:
            return {"ledger_id": lid,
                    "install_location": meta.get("安装位置", ""),
                    "twin_name": meta.get("孪生体实例名称", ""),
                    **meta}, None

    scored: list[tuple[int, str]] = []
    for lid, meta in catalog.items():
        score = -1
        candidates: list[tuple[str, int, int, int]] = [
            (str(meta.get("canonical_name_zh", "")), 128, 103, 93),
            (str(meta.get("system_name", "")), 130, 105, 95),
            (str(meta.get("display_name_en", "")), 125, 100, 90),
            (str(meta.get("安装位置", "")), 120, 95, 85),
            (str(meta.get("孪生体实例名称", "")), 115, 90, 80),
        ]
        candidates.extend((alias, 110, 88, 78) for alias in meta.get("aliases_en", []))
        candidates.extend((alias, 108, 86, 76) for alias in meta.get("aliases_zh", []))

        for candidate, exact_score, contains_score, prefix_score in candidates:
            candidate_score = _score_candidate(query_norm, candidate, exact_score, contains_score, prefix_score)
            if candidate_score > score:
                score = candidate_score
        if score >= 0:
            scored.append((score, lid))

    if not scored:
        hints = ("位置", "区域", "大厅", "会议室", "机房", "侧", "层", "东", "西", "南", "北", "room", "hall", "area", "side", "floor")
        if any(h in query_raw for h in hints):
            return None, "location_no_device"
        return None, "device_not_found"

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score = scored[0][0]
    top = [lid for s, lid in scored if s == top_score]
    if len(top) > 1:
        return None, "ambiguous_device"

    lid = top[0]
    meta = catalog[lid]
    return {"ledger_id": lid,
            "install_location": meta.get("安装位置", ""),
            "twin_name": meta.get("孪生体实例名称", ""),
            **meta}, None


def _extract_temperature_from_timeseries(data: dict[str, Any]) -> float | None:
    temperature_field_names = {_normalize_text(candidate) for candidate in _TEMPERATURE_FIELD_NAMES}
    for key, value in data.items():
        if _normalize_text(str(key)) not in temperature_field_names:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _build_mcp_missing_data_reply(locale: str, backend_message: str) -> str:
    message = str(backend_message or "").strip() or _message(locale, "failure_reply")
    return _message(locale, "mcp_missing_data_reply", message=message)


def _query_temperature_via_mcp(
    token: str,
    base_url: str | None,
    device_info: dict[str, Any],
    preferred_twin_id: str | None = None,
) -> tuple[float | None, dict[str, Any] | None, str | None]:
    invoke_script = SKILLS_ROOT / "ruisi-twinioc-command-skill" / "scripts" / "invoke_skill.py"
    if not invoke_script.exists():
        return None, None, ""

    twin_id = str(preferred_twin_id or "").strip() or _get_twin_id(device_info)
    twin_name = _get_twin_name(device_info)
    if not twin_id and not twin_name:
        return None, None, ""

    mcp_args: dict[str, Any] = {"token": token}
    if twin_id:
        mcp_args["twinId"] = twin_id
    else:
        mcp_args["twinName"] = twin_name

    cmd = [
        *_build_python_cmd(invoke_script),
        "--token", token,
        "--base-url", _normalize_base_url(base_url),
        "--mcp-tool", _TEMPERATURE_MCP_TOOL,
        "--mcp-args", json.dumps(mcp_args, ensure_ascii=False),
    ]
    exit_code, output = _run_capture(cmd)
    if exit_code != 0 or not output.strip():
        return None, None, ""

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None, None, ""

    if not isinstance(parsed, dict):
        return None, None, ""

    message = str(parsed.get("Message") or "").strip()
    if message:
        return None, parsed, message

    data = parsed.get("Data")
    if isinstance(data, dict):
        return _extract_temperature_from_timeseries(data), parsed, None
    return None, parsed, None


def _run(cmd: list[str]) -> int:
    """Run a subprocess, forwarding its stdout/stderr to our own. Return exit code."""
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0 and result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def _run_capture(cmd: list[str]) -> tuple[int, str]:
    """Run a subprocess and return (exit_code, stdout)."""
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0 and result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode, result.stdout or ""


def _build_python_cmd(script_path: Path) -> list[str]:
    return [sys.executable, "-X", "utf8", str(script_path)]


def _find_matched_temperature_rule(token: str, device_name: str, temperature: float) -> dict[str, Any] | None:
    recorder_script = SKILLS_ROOT / "ruisi-twinioc-opeationrule-skill" / "scripts" / "invoke_recorder.py"
    if not recorder_script.exists():
        return None

    cmd = [
        *_build_python_cmd(recorder_script),
        "--match-temperature",
        "--token",
        token,
        "--device-name",
        device_name,
        "--temperature-value",
        str(temperature),
    ]
    exit_code, output = _run_capture(cmd)
    if exit_code != 0 or not output.strip():
        return None

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None

    matches = parsed.get("matches") if isinstance(parsed, dict) else None
    if not isinstance(matches, list) or not matches:
        return None
    latest_match = matches[-1]
    return latest_match if isinstance(latest_match, dict) else None


def _save_pending_rule_action(token: str, matched_rule: dict[str, Any]) -> None:
    recorder_script = SKILLS_ROOT / "ruisi-twinioc-opeationrule-skill" / "scripts" / "invoke_recorder.py"
    if not recorder_script.exists():
        return

    parsed_rule = matched_rule.get("parsed_rule") if isinstance(matched_rule, dict) else None
    if not isinstance(parsed_rule, dict):
        return

    execute_query = str(parsed_rule.get("execute_query") or "").strip()
    if not execute_query:
        return

    confirmation_text = str(matched_rule.get("confirmation_text") or "").strip()
    cmd = [
        *_build_python_cmd(recorder_script),
        "--save-pending",
        "--token",
        token,
        "--source",
        "temperature",
        "--confirmation-text",
        confirmation_text,
        "--execute-query",
        execute_query,
        "--matched-rule-json",
        json.dumps(matched_rule, ensure_ascii=False),
    ]
    _run_capture(cmd)


def _clear_pending_rule_action(token: str) -> None:
    recorder_script = SKILLS_ROOT / "ruisi-twinioc-opeationrule-skill" / "scripts" / "invoke_recorder.py"
    if not recorder_script.exists():
        return

    cmd = [
        *_build_python_cmd(recorder_script),
        "--clear-pending",
        "--token",
        token,
    ]
    _run_capture(cmd)


# ---------------------------------------------------------------------------
# MCP 缓存
# ---------------------------------------------------------------------------

def _cache_key(tool: str, mcp_args_obj: dict) -> str:
    """生成缓存键：工具名 + 参数（按 key 排序后的 JSON）。"""
    args_normalized = json.dumps(mcp_args_obj, ensure_ascii=False, sort_keys=True)
    return f"{tool}:{args_normalized}"


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {"version": CACHE_SCHEMA_VERSION, "last_token": "", "entries": {}}
    try:
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": CACHE_SCHEMA_VERSION, "last_token": "", "entries": {}}
    if not isinstance(cache, dict) or cache.get("version") != CACHE_SCHEMA_VERSION:
        return {"version": CACHE_SCHEMA_VERSION, "last_token": "", "entries": {}}
    return cache


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache["version"] = CACHE_SCHEMA_VERSION
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_temperature(args: argparse.Namespace) -> int:
    """通过 MCP 工具查询温度传感器，并保留本地设备解析与规则匹配。"""
    locale = _normalize_locale(getattr(args, "locale", None), getattr(args, "device_query", None))
    if not _DEFAULT_ENTITY_ALIAS_FILE.exists():
        print(json.dumps({"success": False, "reply": _message(locale, "catalog_missing", path=_DEFAULT_ENTITY_ALIAS_FILE), "locale": locale}, ensure_ascii=False, indent=2))
        return 1

    target_ledger_id = getattr(args, "target_ledger_id", None) or _DEFAULT_TARGET_LEDGER_ID

    device_info, error_reply = _resolve_device(
        user_input=getattr(args, "device_query", None),
        fallback_ledger_id=target_ledger_id,
    )
    if device_info is None:
        print(json.dumps({"success": False, "reply": _message(locale, str(error_reply)), "locale": locale}, ensure_ascii=False, indent=2))
        return 1

    resolved_ledger_id = _pick_resolved_ledger_id(device_info, locale)
    if not resolved_ledger_id:
        print(json.dumps({"success": False, "reply": _message(locale, "device_not_found"), "locale": locale}, ensure_ascii=False, indent=2))
        return 1

    temperature, mcp_result, backend_message = _query_temperature_via_mcp(
        token=args.token,
        base_url=getattr(args, "base_url", None),
        device_info=device_info,
        preferred_twin_id=resolved_ledger_id,
    )

    if backend_message:
        print(
            json.dumps(
                {
                    "success": False,
                    "reply": _build_mcp_missing_data_reply(locale, backend_message),
                    "error": "mcp_missing_data",
                    "backend_message": backend_message,
                    "resolved_ledger_id": resolved_ledger_id,
                    "twin_name": _get_twin_name(device_info),
                    "locale": locale,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    if temperature is None:
        failure_key = "temperature_field_missing" if isinstance(mcp_result, dict) else "failure_reply"
        print(json.dumps({"success": False, "reply": _message(locale, failure_key), "locale": locale}, ensure_ascii=False, indent=2))
        return 1

    match_device_name = _get_match_name(device_info)
    device_name = _get_display_device_name(device_info, locale)
    temperature_text = _normalize_threshold_text(temperature)
    reply = _message(locale, "temperature_reply", device_name=device_name, temperature=temperature_text)

    payload: dict[str, Any] = {
        "success": True,
        "reply": reply,
        "temperature": temperature,
        "device_name": device_name,
        "system_name": str(device_info.get("system_name") or device_name),
        "matched_device_name": match_device_name,
        "resolved_ledger_id": resolved_ledger_id,
        "twin_name": str((mcp_result or {}).get("TwinName") or _get_twin_name(device_info) or ""),
        "twin_id": str((mcp_result or {}).get("TwinId") or resolved_ledger_id or _get_twin_id(device_info) or ""),
        "locale": locale,
    }

    matched_rule = _find_matched_temperature_rule(args.token, match_device_name, temperature)
    if matched_rule:
        parsed_rule = matched_rule.get("parsed_rule") if isinstance(matched_rule, dict) else None
        confirmation_text = str(matched_rule.get("confirmation_text") or "").strip()
        if isinstance(parsed_rule, dict):
            confirmation_text_en = _build_rule_confirmation_text(locale, device_name, temperature, parsed_rule)
            if locale == "en-US":
                confirmation_text = confirmation_text_en
            matched_rule["confirmation_text_en"] = confirmation_text_en
        if confirmation_text:
            payload["reply"] = f"{reply}{_message(locale, 'rule_reply_joiner')}{confirmation_text}"
        payload["rule_match"] = matched_rule
        _save_pending_rule_action(args.token, matched_rule)
    else:
        _clear_pending_rule_action(args.token)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_mcp(args: argparse.Namespace) -> int:
    """Route MCP tool call to ruisi-twinioc-command-skill, with result caching."""
    locale = _normalize_locale(getattr(args, "locale", None))
    tool = args.mcp_tool
    if tool not in _SUPPORTED_MCP_TOOLS:
        print(json.dumps({"success": False, "error": _message(locale, "unsupported_tool", tool=tool), "locale": locale}, ensure_ascii=False, indent=2))
        return 1

    invoke_script = SKILLS_ROOT / "ruisi-twinioc-command-skill" / "scripts" / "invoke_skill.py"
    if not invoke_script.exists():
        print(
            json.dumps(
                {"success": False, "error": _message(locale, "invoke_missing", path=invoke_script), "locale": locale},
                ensure_ascii=False, indent=2,
            )
        )
        return 1

    mcp_args_raw = getattr(args, "mcp_args", "{}")
    try:
        mcp_args_obj = json.loads(mcp_args_raw)
    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                {"success": False, "error": _message(locale, "mcp_args_invalid", error=exc), "locale": locale},
                ensure_ascii=False, indent=2,
            )
        )
        return 1

    # Ensure token is present in mcp_args
    if "token" not in mcp_args_obj:
        mcp_args_obj["token"] = args.token

    cmd = [
        *_build_python_cmd(invoke_script),
        "--token", args.token,
        "--base-url", _normalize_base_url(getattr(args, "base_url", None)),
        "--mcp-tool", tool,
        "--mcp-args", json.dumps(mcp_args_obj, ensure_ascii=False),
    ]

    # 实时数据类工具：跳过缓存，直接调用
    if tool in _NO_CACHE_TOOLS:
        return _run(cmd)

    # 可缓存工具：检查 token 变化 + 命中判断
    cache = _load_cache()
    if cache.get("last_token") != args.token:
        # token 变化，清空全部缓存
        cache = {"version": CACHE_SCHEMA_VERSION, "last_token": args.token, "entries": {}}

    key = _cache_key(tool, mcp_args_obj)
    if key in cache["entries"]:
        # 缓存命中：直接输出缓存结果
        print(cache["entries"][key], end="")
        return 0

    # 缓存未命中：调用子进程，存储结果
    exit_code, output = _run_capture(cmd)
    if exit_code == 0 and output.strip():
        cache["entries"][key] = output
        _save_cache(cache)
    if output:
        print(output, end="")
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TwinEasy unified data query (read-only, no instruction sending)",
    )
    parser.add_argument("--token", required=True, help="孪易场景 token（可用 gj6mxa）")
    parser.add_argument("--base-url", default=None, help="孪易服务基础地址，默认 http://test.twinioc.net")
    # MCP 查询模式
    parser.add_argument(
        "--mcp-tool",
        default=None,
        help=(
            "要调用的 MCP 工具名称。"
            "支持：get_scene_info / get_twin_category_data / get_twin_category / "
            "get_scene_context / get_bind_video_instance_names / get_twin_realtime_time_series_data"
        ),
    )
    parser.add_argument(
        "--mcp-args",
        default="{}",
        help="MCP 工具参数 JSON 字符串，如 '{\"twinCategoryName\": \"可控摄像头\"}'",
    )
    # 温度查询模式
    parser.add_argument(
        "--device-query",
        default=None,
        help="用户输入，通过中文规范名、英文展示名或中英文别名匹配设备（不填则使用默认台账 ID）",
    )
    parser.add_argument(
        "--target-ledger-id",
        default=None,
        help="直接指定默认传感器 ledger ID（与 --device-query 二选一）",
    )
    parser.add_argument("--locale", default=None, help="可选语言标识，如 zh-CN 或 en-US")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.mcp_tool:
        return _run_mcp(args)
    return _run_temperature(args)


if __name__ == "__main__":
    raise SystemExit(main())
