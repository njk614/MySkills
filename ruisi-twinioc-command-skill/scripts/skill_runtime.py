from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx


SKILL_NAME = "twinioc_command_executor"
HTTP_TIMEOUT = float(os.getenv("SKILL_HTTP_TIMEOUT", "120"))
DEFAULT_TWINEASY_SERVER_URL = os.getenv("TWINEASY_SERVER_URL", "http://test.twinioc.net/api/editor").rstrip("/")

# ---------------------------------------------------------------------------
# 指令展示文本映射（合并 A/B/C/D 系列与 E 系列）
# ---------------------------------------------------------------------------

# 无参数指令：直接使用固定展示文本
NO_ARG_COMMAND_TEXT: dict[str, str] = {
    # A 系列
    "A03": "层级切换：下一层",
    "A04": "层级切换：上一层",
    "A05": "层级切换：第一层",
    "A06": "层级切换：最后一层",
    "A09": "场景复位",
    "A13": "时间轴：播放",
    "A14": "时间轴：暂停",
    "A20": "图层全部显示",
    "A21": "图层全部隐藏",
    "A31": "停止演示",
    "A32": "暂停演示",
    "A33": "上一步演示",
    "A34": "下一步演示",
    "A35": "重新演示",
    "A36": "告警信息：当前",
    "A37": "告警信息：历史",
    "A38": "告警信息选中",
    # B 系列
    "B03": "取消选中",
    "B04": "对象下钻",
    "B05": "对象上卷",
    # E 系列
    "E05": "视频：视频上一页",
    "E06": "视频：视频下一页",
    "E08": "视频：下一个视频",
    "E09": "视频：上一个视频",
    "E10": "视频：第一个视频",
    "E11": "视频：末一个视频",
    "E17": "事件：下一个事件",
    "E18": "事件：上一个事件",
    "E19": "事件：第一个事件",
    "E20": "事件：末一个事件",
    "E22": "回放：暂停",
    "E23": "回放：播放",
    "E28": "单路云台：左转",
    "E29": "单路云台：右转",
    "E30": "单路云台：抬头",
    "E31": "单路云台：低头",
    "E32": "单路云台：拉近",
    "E33": "单路云台：拉远",
}

# 带参数指令：去掉编码后直接使用冒号后内容作为展示文本
DIRECT_INFO_PREFIXES: set[str] = {
    # A/B/C 系列
    "A01", "A02", "A07", "A08", "A10", "A11", "A12", "A15", "A16", "A17", "A18",
    "A19", "A22", "A23", "A24", "A25", "A26", "A27", "A28", "A29", "A39",
    "B01", "B02", "B06", "B07", "B08", "B09", "B10", "C01", "C02",
    # E 系列
    "E01", "E02", "E03", "E04", "E07",
    "E12", "E13", "E14", "E15", "E16",
    "E21", "E24", "E25", "E26", "E27",
    "E34",
}

DEMO_PREFIXES: set[str] = {"A30"}


class SkillRuntimeError(Exception):
    pass


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _safe_json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 指令解析与执行计划构建
# ---------------------------------------------------------------------------

def _normalize_command_token(command: str) -> str:
    return str(command or "").strip().upper().rstrip("：:")


def _get_command_prefix(command: str) -> str:
    return _normalize_command_token(command)[:3]


def _normalize_instruction_command(command: str) -> str:
    stripped = str(command or "").strip()
    if not stripped:
        return ""
    command_prefix = _get_command_prefix(stripped)
    if command_prefix in NO_ARG_COMMAND_TEXT:
        return command_prefix
    return stripped


def _extract_info(command: str) -> str:
    parts = command.split("：", 1)
    if len(parts) > 1:
        return parts[1].strip()
    return command.strip() if command else ""


def _get_display_text(command: str) -> str:
    command_prefix = _get_command_prefix(command)
    if command_prefix in NO_ARG_COMMAND_TEXT:
        return NO_ARG_COMMAND_TEXT[command_prefix]
    if "：" not in command:
        return "执行失败，失败原因：" + _normalize_command_token(command)
    extracted = _extract_info(command)
    if command_prefix in DIRECT_INFO_PREFIXES:
        return extracted
    if command_prefix in DEMO_PREFIXES:
        return "演示汇报" + extracted
    return "执行失败，失败原因：" + command


def _process_single_command(command: str) -> str:
    command_prefix = _get_command_prefix(command)

    # D 系列：查询结果展示
    if command.startswith("D"):
        if "：" in command:
            return f"为您查找到相关内容如下：{command.split('：', 1)[1].strip()}"
        if len(command) >= 4:
            return f"为您查找到相关内容如下：{command[3:]}"
        return "执行失败，字符串长度不足"

    # E35：摄像头名称列表查询
    if command_prefix == "E35":
        if "：" in command:
            names_part = command.split("：", 1)[1].strip()
            if names_part.startswith("名称："):
                names_part = names_part[3:].strip()
            names = [n.strip() for n in names_part.split("，") if n.strip()]
            cnt = len(names)
            return f"为您查找到相关内容如下：{'、'.join(names)}；共{cnt}个"
        return "为您查找到相关内容如下：（无数据）"

    return _get_display_text(command)


def _extract_last_bracket_content(text: str) -> str:
    last_close_idx = text.rfind("]")
    if last_close_idx == -1:
        return ""
    last_open_idx = text.rfind("[", 0, last_close_idx)
    if last_open_idx == -1:
        return ""
    bracket_content = text[last_open_idx + 1:last_close_idx].strip()
    if not bracket_content:
        return ""
    normalized_content = bracket_content.replace("&", "$")
    commands = normalized_content.split("$")
    valid_commands = [command.strip() for command in commands if command.strip()]
    return "$".join(valid_commands)


def _extract_last_bracket_raw_content(text: str) -> str:
    last_close_idx = text.rfind("]")
    if last_close_idx == -1:
        return ""
    last_open_idx = text.rfind("[", 0, last_close_idx)
    if last_open_idx == -1:
        return ""
    return text[last_open_idx + 1:last_close_idx].strip()


def _build_execution_plan(agent_text: str) -> tuple[str, str]:
    raw_instruction_order = _extract_last_bracket_content(agent_text)
    raw_commands = raw_instruction_order.strip().split("$") if raw_instruction_order.strip() else []
    normalized_commands = [_normalize_instruction_command(cmd) for cmd in raw_commands if cmd.strip()]
    instruction_order = "$".join(cmd.strip() for cmd in raw_commands if cmd.strip())

    has_failure = False
    failure_result = ""
    results: list[str] = []

    for index, command in enumerate(normalized_commands, 1):
        current = command.strip()
        if not current:
            continue
        content = _process_single_command(current)
        if "执行失败" in content:
            has_failure = True
            failure_result = content
            break
        results.append(f"{index}、{content}")

    if has_failure:
        final_result = failure_result
    elif results:
        first_cmd = normalized_commands[0].strip() if normalized_commands else ""
        first_prefix = _get_command_prefix(first_cmd)
        # D 系列查询和 E35 摄像头列表查询：不加"规划执行计划"前缀
        is_query_only = first_cmd.startswith("D") or first_prefix == "E35"
        if is_query_only:
            first_result = results[0]
            final_result = first_result.split("、", 1)[1] if "、" in first_result else first_result
        else:
            final_result = "根据最优策略，已经为您规划如下执行计划：\n" + "\n".join(results)
    else:
        final_result = "未识别出有效指令，请先查询场景有哪些内容再查找"

    return final_result, instruction_order


def _expand_instruction_order(instruction_order: str) -> str:
    """将指令串中的无参指令码展开为完整形式，如 A04 → A04：层级切换：上一层。"""
    if not instruction_order:
        return ""
    expanded = []
    for cmd in instruction_order.split("$"):
        cmd = cmd.strip()
        prefix = _get_command_prefix(cmd)
        if prefix in NO_ARG_COMMAND_TEXT and "：" not in cmd:
            expanded.append(f"{prefix}：{NO_ARG_COMMAND_TEXT[prefix]}")
        else:
            expanded.append(cmd)
    return "$".join(expanded)


def _is_e_series(instruction_order: str) -> bool:
    """判断指令串是否为 E 系列（视频监控）。"""
    if not instruction_order:
        return False
    first_cmd = instruction_order.split("$")[0].strip()
    prefix = _get_command_prefix(first_cmd)
    return bool(prefix) and prefix[0] == "E"


def _build_json_data(instruction_order: str, query: str, plan_text: str) -> str:
    """构建 SendInstruction 的 jsonData 字段。

    A/B/C/D 系列格式：{expanded_order}$&{query}$&{plan_text}
    E 系列格式：       {expanded_order}$&{plan_text}
    """
    expanded = _expand_instruction_order(instruction_order)
    if _is_e_series(instruction_order):
        return f"{expanded}$&{plan_text}"
    return f"{expanded}$&{query}$&{plan_text}"


# ---------------------------------------------------------------------------
# HTTP 发送
# ---------------------------------------------------------------------------

async def _send_instruction(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    instruction_order: str,
    plan_text: str,
) -> Any:
    json_data = _build_json_data(instruction_order, query, plan_text)
    await asyncio.sleep(1)
    response = await client.post(
        f"{DEFAULT_TWINEASY_SERVER_URL}/v1/location/SendInstruction",
        headers={"Content-Type": "application/json", "Accept": "text/plain"},
        json={
            "token": token,
            "jsonData": json_data,
        },
    )
    if response.status_code >= 400:
        raise SkillRuntimeError(f"孪易指令发送失败: {response.text}")
    return _safe_json_loads(response.text) or response.text


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

async def execute_command(
    token: str,
    query: str,
    agent_output: str,
    execute_instruction: bool = True,
    debug: bool = False,
) -> dict[str, Any]:
    """接收 AI 已生成的指令串（agent_output），执行 SendInstruction 并返回结果。

    agent_output 应为 AI 按照 SKILL.md 中指令库规则生成的原始文本，
    例如 "[A02：层级切换：楼层8&B02：选中对象：摄像头01]" 或 "[E34：筛选：大会议室摄像头2]"。
    """
    if not token:
        raise SkillRuntimeError("token 不能为空")
    if not query:
        raise SkillRuntimeError("query 不能为空")
    if not agent_output:
        raise SkillRuntimeError("agent_output 不能为空")

    plan_text, instruction_order = _build_execution_plan(agent_output)
    json_data = _build_json_data(instruction_order, query, plan_text)

    execution_result: Any = None
    if execute_instruction and instruction_order:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            execution_result = await _send_instruction(client, token, query, instruction_order, plan_text)

    result: dict[str, Any] = {
        "jsonData": json_data,
        "plan_text": plan_text,
        "instruction_order": instruction_order,
    }
    if execute_instruction:
        result["execution_result"] = execution_result
    if debug:
        result["debug_info"] = {
            "agent_raw_output": agent_output,
            "send_instruction_payload": {
                "token": token,
                "jsonData": json_data,
            },
        }
    return result
