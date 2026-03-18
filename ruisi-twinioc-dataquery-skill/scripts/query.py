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
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request

# Skill root:  e:\AI\Skills\ruisi-twinioc-dataquery-skill\scripts\query.py  → parent.parent
SKILL_ROOT = Path(__file__).resolve().parent.parent

# Workspace root (parent of skill root)
SKILLS_ROOT = SKILL_ROOT.parent

# MCP 查询结果缓存文件（token 变化时全部清空）
CACHE_FILE = SKILL_ROOT / ".runtime" / "mcp_cache.json"

# 实时/动态数据类工具，跳过缓存
_NO_CACHE_TOOLS: frozenset[str] = frozenset(
    {
        "get_scene_context",  # 含会话历史，实时变化
    }
)

# MCP tools served by the twinioc_interactive_command runtime
_TWINIOC_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "get_scene_info",
        "get_twin_category_data",
        "get_twin_category",
        "get_scene_context",
    }
)

# MCP tools served by the video_surveillance_command runtime
_VIDEO_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "get_bind_video_instance_names",
    }
)

# ---------------------------------------------------------------------------
# 温度传感器查询（内联逻辑，不依赖外部 skill）
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "http://test.twinioc.net/api/editor/v1"
_DEFAULT_LOCATION_ID = "dyo6vaow6203kx09"
_TWIN_CATEGORY_CONFIG_ID = "hcwn2ha6p49661rm"
_QUERY_LEVEL_ID = "gez4ermd715t31le"
_DEFAULT_TARGET_LEDGER_ID = "R3nazZz8Pyb6o7uc"
_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_RETRY_INTERVAL = 1.0
_DEFAULT_DEVICE_DATA_FILE = SKILL_ROOT / "data_organized.json"

_QUERY_DIMENSION_NAMES = ("时间", "用户台账ID", "温度", "湿度", "电池电量", "区域")

_FAILURE_REPLY = "温度查询失败，请稍后重试。"
_DEVICE_NOT_FOUND_REPLY = "设备不存在。"
_LOCATION_NO_DEVICE_REPLY = "当前位置没有设备。"
_AMBIGUOUS_DEVICE_REPLY = "当前位置存在多个设备，请提供更具体的孪生体实例名称。"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


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


def _load_device_catalog(device_data_file: Path) -> dict[str, dict[str, str]]:
    with device_data_file.open("r", encoding="utf-8") as f:
        parsed = json.load(f)
    if not isinstance(parsed, dict):
        raise ValueError("device catalog root must be an object")
    catalog: dict[str, dict[str, str]] = {}
    for ledger_id, meta in parsed.items():
        if not isinstance(ledger_id, str) or not isinstance(meta, dict):
            continue
        catalog[ledger_id] = {
            "安装位置": str(meta.get("安装位置", "")).strip(),
            "孪生体实例名称": str(meta.get("孪生体实例名称", "")).strip(),
        }
    return catalog


def _resolve_device(
    user_input: str | None,
    fallback_ledger_id: str,
    device_data_file: Path,
) -> tuple[dict[str, str] | None, str | None]:
    """返回 (device_info, error_reply)。device_info 包含 ledger_id / install_location / twin_name。"""
    try:
        catalog = _load_device_catalog(device_data_file)
    except Exception:
        return None, _FAILURE_REPLY

    if not user_input or not user_input.strip():
        meta = catalog.get(fallback_ledger_id, {})
        return {"ledger_id": fallback_ledger_id,
                "install_location": meta.get("安装位置", ""),
                "twin_name": meta.get("孪生体实例名称", "")}, None

    query_raw = user_input.strip()
    query_norm = _normalize_text(query_raw)
    if not query_norm:
        return None, _DEVICE_NOT_FOUND_REPLY

    # 直接匹配 ledger_id
    for lid in catalog:
        if _normalize_text(lid) == query_norm:
            meta = catalog[lid]
            return {"ledger_id": lid,
                    "install_location": meta.get("安装位置", ""),
                    "twin_name": meta.get("孪生体实例名称", "")}, None

    scored: list[tuple[int, str]] = []
    for lid, meta in catalog.items():
        loc_norm = _normalize_text(meta.get("安装位置", ""))
        twin_norm = _normalize_text(meta.get("孪生体实例名称", ""))
        score = -1
        if twin_norm and query_norm == twin_norm:
            score = 120
        elif loc_norm and query_norm == loc_norm:
            score = 110
        elif twin_norm and _contains_with_numeric_boundary(query_norm, twin_norm):
            score = 100
        elif loc_norm and loc_norm in query_norm:
            score = 90
        elif twin_norm and query_norm in twin_norm:
            score = 80
        elif loc_norm and query_norm in loc_norm:
            score = 70
        if score >= 0:
            scored.append((score, lid))

    if not scored:
        hints = ("位置", "区域", "大厅", "会议室", "机房", "侧", "层", "东", "西", "南", "北")
        if any(h in query_raw for h in hints):
            return None, _LOCATION_NO_DEVICE_REPLY
        return None, _DEVICE_NOT_FOUND_REPLY

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score = scored[0][0]
    top = [lid for s, lid in scored if s == top_score]
    if len(top) > 1:
        return None, _AMBIGUOUS_DEVICE_REPLY

    lid = top[0]
    meta = catalog[lid]
    return {"ledger_id": lid,
            "install_location": meta.get("安装位置", ""),
            "twin_name": meta.get("孪生体实例名称", "")}, None


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, Any | None]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url, data=data, method="POST",
        headers={"accept": "text/plain", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
            return resp.getcode(), json.loads(body) if body else None
    except error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def _query_temperature_value(
    base_url: str,
    location_id: str,
    target_ledger_id: str,
    timeout: float,
    max_attempts: int,
    retry_interval: float,
) -> float | None:
    url = (f"{base_url.rstrip('/')}/public/location/{location_id}/"
           "twinTypeDistinguish/TwinTimeSeries/batchQueryData")
    payload = {
        "batchQueryDataRequest": [{
            "twinCategoryConfigID": _TWIN_CATEGORY_CONFIG_ID,
            "queryTimeDataRequest": {
                "isRealTime": True,
                "dimensions": [{"columnName": n} for n in _QUERY_DIMENSION_NAMES],
            },
        }],
        "levelID": _QUERY_LEVEL_ID,
    }
    for attempt in range(max(1, max_attempts)):
        status, parsed = _post_json(url, payload, timeout)
        if status and 200 <= status < 300 and isinstance(parsed, dict):
            data_block = parsed.get("data", {})
            for model in (data_block.get("batchQueryDataModels") or []):
                table = model.get("data") if isinstance(model, dict) else None
                if not isinstance(table, list) or len(table) < 2:
                    continue
                header = table[0]
                try:
                    lid_idx = header.index("用户台账ID")
                    tmp_idx = header.index("温度")
                except (ValueError, TypeError):
                    continue
                for row in table[1:]:
                    if not isinstance(row, list):
                        continue
                    if lid_idx >= len(row) or tmp_idx >= len(row):
                        continue
                    if str(row[lid_idx]) != target_ledger_id:
                        continue
                    try:
                        return float(row[tmp_idx])
                    except (TypeError, ValueError):
                        return None
        if attempt + 1 < max(1, max_attempts):
            time.sleep(max(0.0, retry_interval))
    return None


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
        return {"last_token": "", "entries": {}}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_token": "", "entries": {}}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_temperature(args: argparse.Namespace) -> int:
    """直接查询温度传感器，不依赖外部脚本。"""
    device_data_file = Path(args.device_data_file) if getattr(args, "device_data_file", None) else _DEFAULT_DEVICE_DATA_FILE
    if not device_data_file.exists():
        print(json.dumps({"success": False, "reply": f"设备台账文件不存在: {device_data_file}"}, ensure_ascii=False, indent=2))
        return 1

    target_ledger_id = getattr(args, "target_ledger_id", None) or _DEFAULT_TARGET_LEDGER_ID

    device_info, error_reply = _resolve_device(
        user_input=getattr(args, "device_query", None),
        fallback_ledger_id=target_ledger_id,
        device_data_file=device_data_file,
    )
    if device_info is None:
        print(json.dumps({"success": False, "reply": error_reply}, ensure_ascii=False, indent=2))
        return 1

    temperature = _query_temperature_value(
        base_url=_DEFAULT_BASE_URL,
        location_id=getattr(args, "location_id", _DEFAULT_LOCATION_ID),
        target_ledger_id=device_info["ledger_id"],
        timeout=getattr(args, "timeout", 100.0),
        max_attempts=getattr(args, "max_attempts", _DEFAULT_MAX_ATTEMPTS),
        retry_interval=_DEFAULT_RETRY_INTERVAL,
    )

    if temperature is None:
        print(json.dumps({"success": False, "reply": _FAILURE_REPLY}, ensure_ascii=False, indent=2))
        return 1

    device_name = device_info.get("install_location") or device_info.get("twin_name") or device_info["ledger_id"]
    reply = f"{device_name}当前温度{temperature}℃"

    payload: dict[str, Any] = {
        "success": True,
        "reply": reply,
        "temperature": temperature,
        "device_name": device_name,
    }

    matched_rule = _find_matched_temperature_rule(args.token, device_name, temperature)
    if matched_rule:
        confirmation_text = str(matched_rule.get("confirmation_text") or "").strip()
        if confirmation_text:
            payload["reply"] = f"{reply}。{confirmation_text}"
        payload["rule_match"] = matched_rule
        _save_pending_rule_action(args.token, matched_rule)
    else:
        _clear_pending_rule_action(args.token)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_mcp(args: argparse.Namespace) -> int:
    """Route MCP tool call to the correct invoke_skill.py, with result caching."""
    tool = args.mcp_tool

    if tool in _VIDEO_MCP_TOOLS:
        invoke_script = SKILLS_ROOT / "video_surveillance_command" / "scripts" / "invoke_skill.py"
    else:
        # Default: twinioc_interactive_command handles all other MCP tools
        invoke_script = SKILLS_ROOT / "twinioc_interactive_command" / "scripts" / "invoke_skill.py"

    if not invoke_script.exists():
        print(
            json.dumps(
                {"success": False, "error": f"invoke_skill.py 不存在: {invoke_script}"},
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
                {"success": False, "error": f"--mcp-args JSON 解析失败: {exc}"},
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
        cache = {"last_token": args.token, "entries": {}}

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
    sub = parser.add_subparsers(dest="mode", required=True)

    # ── temperature subcommand ────────────────────────────────────────────────
    temp = sub.add_parser("temperature", help="Query temperature sensor for a device")
    temp.add_argument("--token", required=True, help="孪易场景 token（默认可用 gj6mxa）")
    temp.add_argument(
        "--device-query",
        default=None,
        help="用户输入，通过安装位置或孪生体实例名称匹配设备（不填则使用默认台账）",
    )
    temp.add_argument(
        "--location-id",
        default="dyo6vaow6203kx09",
        help="Location ID（默认 dyo6vaow6203kx09）",
    )
    temp.add_argument(
        "--target-ledger-id",
        default=None,
        help="直接指定用户台账 ID（与 --device-query 二选一）",
    )
    temp.add_argument("--timeout", type=float, default=100.0, help="HTTP 超时秒数")
    temp.add_argument("--max-attempts", type=int, default=5, help="最大重试次数")

    # ── mcp subcommand ────────────────────────────────────────────────────────
    mcp = sub.add_parser("mcp", help="Call an MCP tool and return JSON result")
    mcp.add_argument("--token", required=True, help="孪易场景 token")
    mcp.add_argument(
        "--mcp-tool",
        required=True,
        help=(
            "要调用的 MCP 工具名称。"
            "支持：get_scene_info / get_twin_category_data / get_twin_category / "
            "get_bind_video_instance_names"
        ),
    )
    mcp.add_argument(
        "--mcp-args",
        default="{}",
        help="MCP 工具参数 JSON 字符串，如 '{\"twinCategoryName\": \"可控摄像头\"}'",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.mode == "temperature":
        return _run_temperature(args)
    if args.mode == "mcp":
        return _run_mcp(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
