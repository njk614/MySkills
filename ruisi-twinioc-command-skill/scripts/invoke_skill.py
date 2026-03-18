from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from skill_runtime import SkillRuntimeError, call_mcp_tool, execute_command, get_scene_context  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoke twinioc command executor skill")
    parser.add_argument("--token", required=True, help="孪易场景 token")
    parser.add_argument("--mcp-tool", help="直接调用 MCP 工具名称并返回结果，如 get_scene_info")
    parser.add_argument("--mcp-args", default="{}", help="MCP 工具参数 JSON 字符串")
    parser.add_argument("--query", help="用户输入的自然语言指令")
    parser.add_argument("--agent-output",
                        help="AI 已生成的指令串，如 [A02：层级切换：楼层8&B02：选中对象：摄像头01]")
    parser.add_argument("--no-execute", action="store_true", help="只生成指令与展示文本，不调用 SendInstruction")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        if args.mcp_tool:
            mcp_arguments = json.loads(args.mcp_args)
            if args.mcp_tool == "get_scene_context":
                result = await get_scene_context(args.token)
            else:
                if "token" not in mcp_arguments:
                    mcp_arguments["token"] = args.token
                result = await call_mcp_tool(args.token, args.mcp_tool, mcp_arguments)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if not args.query or not args.agent_output:
            print(
                json.dumps(
                    {"skill_name": "ruisi_twinioc_command_executor", "success": False, "error": "执行指令模式需要 --query 和 --agent-output 参数"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        result = await execute_command(
            token=args.token,
            query=args.query,
            agent_output=args.agent_output,
            execute_instruction=not args.no_execute,
            debug=args.debug,
        )
        if args.debug:
            import sys
            print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        print(result.get("plan_text", ""))
        return 0
    except SkillRuntimeError as exc:
        print(
            json.dumps(
                {"skill_name": "twinioc_command_executor", "success": False, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
