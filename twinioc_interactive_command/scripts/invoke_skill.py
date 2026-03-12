from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from skill_runtime import SkillRuntimeError, invoke_skill  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoke luanyi interactive assistant skill")
    parser.add_argument("--query", required=True, help="用户输入的自然语言指令")
    parser.add_argument("--token", required=True, help="孪易场景 token")
    parser.add_argument(
        "--no-execute",
        action="store_true",
        help="只生成指令与展示文本，不调用 SendInstruction",
    )
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    parser.add_argument("--llm-model", default=None, help="覆盖默认模型名")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        result = await invoke_skill(
            query=args.query,
            token=args.token,
            execute_instruction=not args.no_execute,
            debug=args.debug,
            llm_model=args.llm_model,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SkillRuntimeError as exc:
        print(
            json.dumps(
                {
                    "skill_name": "luanyi_interactive_assistant",
                    "success": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
