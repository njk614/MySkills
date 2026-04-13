from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from skill_runtime import SkillRuntimeError, call_mcp_tool, execute_command, get_scene_context  # noqa: E402


CONFIRMATION_WORDS = {"是", "确认", "好", "好的", "执行", "对", "可以", "行", "yes", "confirm", "ok", "okay", "sure", "goahead", "dothat", "doit"}
NEGATION_WORDS = {"否", "取消", "不", "不要", "算了", "no", "cancel", "stop", "dont", "nevermind", "nope"}

MESSAGES = {
    "zh-CN": {
        "no_pending": "当前没有待确认操作",
        "cancelled": "已取消操作",
        "missing_query": "执行指令模式需要 --query 参数",
        "missing_execute_query": "待确认操作缺少 execute_query",
        "missing_agent_output": "确认执行需要上游 AI 提供 agent_output",
    },
    "en-US": {
        "no_pending": "No pending confirmation found",
        "cancelled": "Operation cancelled",
        "missing_query": "Execution mode requires the --query argument",
        "missing_execute_query": "The pending action does not contain execute_query",
        "missing_agent_output": "Confirming the action requires agent_output from the upstream AI",
    },
}


def _normalize_confirmation_text(query: str) -> str:
    return re.sub(r"[\s，,。；;！？!?~～、'\"`-]", "", query).strip().lower()


def _detect_locale(text: str | None) -> str:
    value = str(text or "")
    if re.search(r"[A-Za-z]", value) and not re.search(r"[\u4e00-\u9fff]", value):
        return "en-US"
    return "zh-CN"


def _message(locale: str, key: str) -> str:
    return MESSAGES.get(locale, MESSAGES["zh-CN"]).get(key) or MESSAGES["zh-CN"][key]


def _matches_intent(query: str, candidates: set[str]) -> bool:
    normalized = _normalize_confirmation_text(query)
    return normalized in candidates


def _is_short_pending_reply_candidate(query: str) -> bool:
    raw = str(query or "").strip()
    if not raw:
        return False
    compact = _normalize_confirmation_text(raw)
    if not compact:
        return False
    words = [item for item in re.split(r"\s+", raw) if item]
    return len(compact) <= 12 and len(words) <= 2


def _is_confirmation_query(query: str) -> bool:
    return _matches_intent(query, CONFIRMATION_WORDS)


def _is_negation_query(query: str) -> bool:
    return _matches_intent(query, NEGATION_WORDS)


def _get_operation_rule_recorder_script() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "ruisi-twinioc-opeationrule-skill" / "scripts" / "invoke_recorder.py"


def _run_recorder_command(arguments: list[str]) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(_get_operation_rule_recorder_script()), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    stdout = result.stdout.strip() if result.stdout else ""
    stderr = result.stderr.strip() if result.stderr else ""
    return {"ok": result.returncode == 0, "stdout": stdout, "stderr": stderr}


def _load_pending_confirmation(token: str) -> dict[str, object] | None:
    response = _run_recorder_command(["--get-pending", "--token", token])
    if not response.get("ok"):
        return None

    try:
        parsed = json.loads(str(response.get("stdout") or ""))
    except json.JSONDecodeError:
        return None

    pending = parsed.get("pending") if isinstance(parsed, dict) else None
    return pending if isinstance(pending, dict) else None


def _clear_pending_confirmation(token: str) -> None:
    _run_recorder_command(["--clear-pending", "--token", token])


def _extract_execute_query_from_pending(pending: dict[str, object]) -> str:
    matched_rule = pending.get("matched_rule") if isinstance(pending, dict) else None
    if not isinstance(matched_rule, dict):
        return ""

    parsed_rule = matched_rule.get("parsed_rule")
    if not isinstance(parsed_rule, dict):
        return ""

    return str(parsed_rule.get("execute_query") or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoke twinioc command executor skill")
    parser.add_argument("--token", required=True, help="孪易场景 token")
    parser.add_argument("--base-url", default=None, help="孪易服务基础地址，默认 http://test.twinioc.net")
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
        original_query = args.query.strip() if args.query else ""
        locale = _detect_locale(original_query)
        if args.mcp_tool:
            mcp_arguments = json.loads(args.mcp_args)
            if args.mcp_tool == "get_scene_context":
                result = await get_scene_context(args.token, base_url=args.base_url)
            else:
                if "token" not in mcp_arguments:
                    mcp_arguments["token"] = args.token
                result = await call_mcp_tool(args.token, args.mcp_tool, mcp_arguments, base_url=args.base_url)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if not original_query:
            print(
                json.dumps(
                    {"skill_name": "ruisi_twinioc_command_executor", "success": False, "error": _message(locale, "missing_query")},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        pending = None
        if _is_short_pending_reply_candidate(original_query):
            pending = _load_pending_confirmation(args.token)
            if pending and (_is_confirmation_query(original_query) or _is_negation_query(original_query)):
                if _is_negation_query(original_query):
                    _clear_pending_confirmation(args.token)
                    print(json.dumps({"message": _message(locale, "cancelled")}, ensure_ascii=False, indent=2))
                    return 0

                execute_query = _extract_execute_query_from_pending(pending)
                if not execute_query:
                    print(
                        json.dumps(
                            {"skill_name": "ruisi_twinioc_command_executor", "success": False, "error": _message(locale, "missing_execute_query")},
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    return 1

                args.query = execute_query

                if not args.agent_output:
                    print(
                        json.dumps(
                            {"skill_name": "ruisi_twinioc_command_executor", "success": False, "error": _message(locale, "missing_agent_output")},
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
            locale=locale,
            base_url=args.base_url,
        )

        if pending is not None and _is_confirmation_query(original_query):
            _clear_pending_confirmation(args.token)

        if args.debug:
            import sys
            print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        # 返回固定 JSON 给前端（不包含分隔标记）
        out = json.dumps({"message": result.get("plan_text", "")}, ensure_ascii=False, indent=2)
        print(out)
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
