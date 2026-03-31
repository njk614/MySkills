#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
COMMAND_SKILL_SCRIPTS = CURRENT_DIR.parent.parent / "ruisi-twinioc-command-skill" / "scripts"
if str(COMMAND_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMAND_SKILL_SCRIPTS))

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


def _parse_json_arg(value: str) -> dict[str, Any]:
    parsed = json.loads(value or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("--mcp-args 必须是 JSON 对象")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ruisi Twinioc spacecount MCP query entry")
    parser.add_argument("--token", required=True, help="场景 token")
    parser.add_argument("--mcp-tool", required=True, help="MCP 工具名称")
    parser.add_argument("--mcp-args", default="{}", help="MCP 工具参数 JSON 字符串")
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

    if "token" not in mcp_args:
        mcp_args["token"] = args.token

    try:
        result = await call_mcp_tool(args.token, tool_name, mcp_args)
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
