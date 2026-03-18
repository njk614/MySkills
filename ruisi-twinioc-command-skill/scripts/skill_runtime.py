from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from itertools import count
from pathlib import Path
from typing import Any

import httpx


SKILL_NAME = "ruisi_twinioc_command_executor"
HTTP_TIMEOUT = float(os.getenv("SKILL_HTTP_TIMEOUT", "120"))
DEFAULT_MCP_BASE_URL = os.getenv("TWINEASY_MCP_BASE_URL", "http://test.twinioc.net/api/editor/mcp").rstrip("/")
DEFAULT_TWINEASY_SERVER_URL = os.getenv("TWINEASY_SERVER_URL", "http://test.twinioc.net/api/editor").rstrip("/")
MCP_AUTH_IN_HEADER = os.getenv("MCP_AUTH_IN_HEADER", "false").lower() == "true"
MCP_PROTOCOL_VERSION = os.getenv("MCP_PROTOCOL_VERSION", "2025-03-26")
MAX_HISTORY_ITEMS = 20
# session 缓存统一存放在 ruisi-twinioc-dataquery-skill 中
_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = _SKILLS_ROOT / "ruisi-twinioc-dataquery-skill" / ".runtime" / "session_store.json"
JSON_RPC_ID_COUNTER = count(1)


@dataclass
class SessionState:
    session_id: str
    token_judge: str = ""
    scene_info: str = ""
    history_inter: list[dict[str, Any]] = field(default_factory=list)
    mcp_session_id: str = ""
    mcp_initialized: bool = False
    updated_at: float = field(default_factory=time.time)

    def reset_for_token(self, token: str) -> None:
        self.token_judge = token
        self.scene_info = ""
        self.history_inter.clear()
        self.mcp_session_id = ""
        self.mcp_initialized = False
        self.updated_at = time.time()


NO_ARG_COMMAND_TEXT: dict[str, str] = {
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
    "B03": "取消选中",
    "B04": "对象下钻",
    "B05": "对象上卷",
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

DIRECT_INFO_PREFIXES: set[str] = {
    "A01", "A02", "A07", "A08", "A10", "A11", "A12", "A15", "A16", "A17", "A18",
    "A19", "A22", "A23", "A24", "A25", "A26", "A27", "A28", "A29", "A39",
    "B01", "B02", "B06", "B07", "B08", "B09", "B10", "C01", "C02",
    "E01", "E02", "E03", "E04", "E07",
    "E12", "E13", "E14", "E15", "E16",
    "E21", "E24", "E25", "E26", "E27",
    "E34",
}

DEMO_PREFIXES: set[str] = {"A30"}


class SkillRuntimeError(Exception):
    pass


def _safe_json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _ensure_runtime_dir() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_session_store() -> dict[str, SessionState]:
    _ensure_runtime_dir()
    if not STATE_FILE.exists():
        return {}
    raw = _safe_json_loads(STATE_FILE.read_text(encoding="utf-8")) or {}
    result: dict[str, SessionState] = {}
    for session_id, payload in raw.items():
        result[session_id] = SessionState(
            session_id=session_id,
            token_judge=payload.get("token_judge", ""),
            scene_info=payload.get("scene_info", ""),
            history_inter=list(payload.get("history_inter", []) or []),
            mcp_session_id=payload.get("mcp_session_id", ""),
            mcp_initialized=bool(payload.get("mcp_initialized", False)),
            updated_at=float(payload.get("updated_at", time.time())),
        )
    return result


def _save_session_store(store: dict[str, SessionState]) -> None:
    _ensure_runtime_dir()
    payload = {session_id: asdict(session) for session_id, session in store.items()}
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_or_create_session(store: dict[str, SessionState], session_id: str) -> SessionState:
    session = store.get(session_id)
    if session:
        return session
    session = SessionState(session_id=session_id)
    store[session_id] = session
    return session


def _get_mcp_headers(token: str, mcp_session_id: str | None = None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token and MCP_AUTH_IN_HEADER:
        headers["Authorization"] = f"Bearer {token}"
    if mcp_session_id:
        headers["Mcp-Session-Id"] = mcp_session_id
    return headers


def _next_json_rpc_id() -> int:
    return next(JSON_RPC_ID_COUNTER)


def _extract_sse_payloads(raw_text: str) -> list[Any]:
    payloads: list[Any] = []
    current_data: list[str] = []

    for line in raw_text.splitlines():
        if not line.strip():
            if current_data:
                joined = "\n".join(current_data)
                parsed = _safe_json_loads(joined)
                if parsed is not None:
                    payloads.append(parsed)
                current_data = []
            continue
        if line.startswith("data:"):
            current_data.append(line[5:].lstrip())

    if current_data:
        joined = "\n".join(current_data)
        parsed = _safe_json_loads(joined)
        if parsed is not None:
            payloads.append(parsed)
    return payloads


def _find_json_rpc_message(payload: Any, request_id: int) -> dict[str, Any] | None:
    if isinstance(payload, list):
        for item in payload:
            matched = _find_json_rpc_message(item, request_id)
            if matched is not None:
                return matched
        return None
    if isinstance(payload, dict) and payload.get("id") == request_id:
        return payload
    return None


def _parse_mcp_response_payload(response: httpx.Response, request_id: int) -> dict[str, Any] | None:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text or ""

    if response.status_code == 202:
        return None

    if "application/json" in content_type:
        parsed = _safe_json_loads(text)
        if parsed is None:
            raise SkillRuntimeError(f"MCP 返回了无法解析的 JSON: {text[:500]}")
        matched = _find_json_rpc_message(parsed, request_id)
        if matched is None:
            raise SkillRuntimeError(f"MCP 未返回匹配请求 {request_id} 的 JSON-RPC 响应: {text[:500]}")
        return matched

    if "text/event-stream" in content_type:
        payloads = _extract_sse_payloads(text)
        matched = _find_json_rpc_message(payloads, request_id)
        if matched is None:
            raise SkillRuntimeError(f"MCP SSE 未返回匹配请求 {request_id} 的 JSON-RPC 响应: {text[:500]}")
        return matched

    parsed = _safe_json_loads(text)
    if parsed is not None:
        matched = _find_json_rpc_message(parsed, request_id)
        if matched is not None:
            return matched
    raise SkillRuntimeError(
        f"MCP 返回了未知响应类型 status={response.status_code} content-type={content_type} body={text[:500]}"
    )


def _normalize_mcp_tool_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result

    content = result.get("content")
    if not isinstance(content, list):
        return result

    texts: list[str] = []
    normalized_items: list[Any] = []
    for item in content:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue
        if item.get("type") == "text":
            text = str(item.get("text", ""))
            texts.append(text)
            parsed = _safe_json_loads(text)
            normalized_items.append(parsed if parsed is not None else text)
        elif item.get("type") == "resource":
            normalized_items.append(item.get("resource", item))
        else:
            normalized_items.append(item)

    if len(normalized_items) == 1:
        return normalized_items[0]
    if texts and len(texts) == len(normalized_items):
        return "\n".join(texts)
    return normalized_items


async def _post_mcp_json_rpc(
    client: httpx.AsyncClient,
    token: str,
    method: str,
    params: dict[str, Any] | None,
    mcp_session_id: str | None = None,
    expect_response: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
    request_id = _next_json_rpc_id()
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if expect_response:
        payload["id"] = request_id

    headers = _get_mcp_headers(token, mcp_session_id)
    response = await client.post(DEFAULT_MCP_BASE_URL, headers=headers, json=payload)

    if response.status_code >= 400:
        response_text = response.text.strip()
        raise SkillRuntimeError(
            f"MCP 请求失败(method={method}) status={response.status_code} url={response.request.url} body={response_text}"
        )

    next_session_id = response.headers.get("Mcp-Session-Id") or mcp_session_id
    parsed = _parse_mcp_response_payload(response, request_id) if expect_response else None
    return parsed, next_session_id


async def _ensure_mcp_initialized(client: httpx.AsyncClient, session: SessionState, token: str) -> None:
    if session.mcp_initialized:
        return

    initialize_response, mcp_session_id = await _post_mcp_json_rpc(
        client=client,
        token=token,
        method="initialize",
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"roots": {}, "sampling": {}},
            "clientInfo": {"name": SKILL_NAME, "version": "1.0.0"},
        },
        mcp_session_id=None,
        expect_response=True,
    )
    if not initialize_response:
        raise SkillRuntimeError("MCP 初始化失败：未收到 initialize 响应")
    if initialize_response.get("error"):
        raise SkillRuntimeError(f"MCP 初始化失败: {initialize_response['error']}")

    session.mcp_session_id = mcp_session_id or ""
    await _post_mcp_json_rpc(
        client=client,
        token=token,
        method="notifications/initialized",
        params=None,
        mcp_session_id=session.mcp_session_id or None,
        expect_response=False,
    )
    session.mcp_initialized = True


async def _invoke_mcp_tool(
    client: httpx.AsyncClient,
    session: SessionState,
    tool_name: str,
    arguments: dict[str, Any],
    token: str,
) -> Any:
    try:
        await _ensure_mcp_initialized(client, session, token)
        response_payload, next_session_id = await _post_mcp_json_rpc(
            client=client,
            token=token,
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
            mcp_session_id=session.mcp_session_id or None,
            expect_response=True,
        )
    except SkillRuntimeError as exc:
        if session.mcp_session_id and "status=404" in str(exc):
            session.mcp_session_id = ""
            session.mcp_initialized = False
            await _ensure_mcp_initialized(client, session, token)
            response_payload, next_session_id = await _post_mcp_json_rpc(
                client=client,
                token=token,
                method="tools/call",
                params={"name": tool_name, "arguments": arguments},
                mcp_session_id=session.mcp_session_id or None,
                expect_response=True,
            )
        else:
            raise

    if next_session_id:
        session.mcp_session_id = next_session_id
    if not response_payload:
        raise SkillRuntimeError(f"MCP 工具调用失败({tool_name})：未收到 tools/call 响应")
    if response_payload.get("error"):
        raise SkillRuntimeError(f"MCP 工具调用失败({tool_name})：{response_payload['error']}")

    result = response_payload.get("result")
    if isinstance(result, dict) and result.get("isError"):
        raise SkillRuntimeError(f"MCP 工具调用失败({tool_name})：{_stringify(result)}")
    return _normalize_mcp_tool_result(result)


async def _fetch_scene_info(client: httpx.AsyncClient, session: SessionState, token: str) -> Any:
    return await _invoke_mcp_tool(client, session, "get_scene_info", {"token": token}, token)


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

    if command.startswith("D"):
        if "：" in command:
            return f"为您查找到相关内容如下：{command.split('：', 1)[1].strip()}"
        if len(command) >= 4:
            return f"为您查找到相关内容如下：{command[3:]}"
        return "执行失败，字符串长度不足"

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
    if not instruction_order:
        return False
    first_cmd = instruction_order.split("$")[0].strip()
    prefix = _get_command_prefix(first_cmd)
    return bool(prefix) and prefix[0] == "E"


def _build_json_data(instruction_order: str, query: str, plan_text: str) -> str:
    expanded = _expand_instruction_order(instruction_order)
    if _is_e_series(instruction_order):
        return f"{expanded}$&{plan_text}"
    return f"{expanded}$&{query}$&{plan_text}"


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
        json={"token": token, "jsonData": json_data},
    )
    if response.status_code >= 400:
        raise SkillRuntimeError(f"孪易指令发送失败: {response.text}")
    return _safe_json_loads(response.text) or response.text


async def get_scene_context(token: str, session_id: str = "default") -> dict[str, Any]:
    if not token:
        raise SkillRuntimeError("token 不能为空")

    store = _load_session_store()
    session = _get_or_create_session(store, session_id)

    if session.token_judge and session.token_judge != token:
        session.reset_for_token(token)

    scene_info_error: str | None = None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        if not session.scene_info or session.token_judge != token:
            try:
                scene_info_raw = await _fetch_scene_info(client, session, token)
                session.scene_info = _stringify(scene_info_raw)
            except SkillRuntimeError as exc:
                scene_info_error = str(exc)
                session.scene_info = json.dumps(
                    {
                        "fallback": True,
                        "message": "scene_info 获取失败，已降级为无场景缓存模式",
                        "reason": scene_info_error,
                    },
                    ensure_ascii=False,
                )
            session.token_judge = token
            session.history_inter = []

    store[session_id] = session
    _save_session_store(store)

    return {
        "scene_info": _safe_json_loads(session.scene_info) or session.scene_info,
        "history_inter": session.history_inter,
        "scene_info_error": scene_info_error,
    }


async def call_mcp_tool(token: str, tool_name: str, arguments: dict[str, Any], session_id: str = "default") -> Any:
    if not token:
        raise SkillRuntimeError("token 不能为空")
    if not tool_name:
        raise SkillRuntimeError("tool_name 不能为空")

    store = _load_session_store()
    session = _get_or_create_session(store, session_id)

    if session.token_judge and session.token_judge != token:
        session.reset_for_token(token)
    elif not session.token_judge:
        session.token_judge = token

    if "token" not in arguments:
        arguments = {**arguments, "token": token}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        result = await _invoke_mcp_tool(client, session, tool_name, arguments, token)

    record = {"tool_call_name": tool_name, "tool_response": result}
    session.history_inter.append(record)
    session.history_inter = session.history_inter[-MAX_HISTORY_ITEMS:]
    session.updated_at = time.time()
    store[session_id] = session
    _save_session_store(store)

    return result


async def execute_command(
    token: str,
    query: str,
    agent_output: str,
    session_id: str = "default",
    execute_instruction: bool = True,
    debug: bool = False,
) -> dict[str, Any]:
    if not token:
        raise SkillRuntimeError("token 不能为空")
    if not query:
        raise SkillRuntimeError("query 不能为空")
    if not agent_output:
        raise SkillRuntimeError("agent_output 不能为空")

    plan_text, instruction_order = _build_execution_plan(agent_text=agent_output)
    json_data = _build_json_data(instruction_order, query, plan_text)

    execution_result: Any = None
    if execute_instruction and instruction_order:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            execution_result = await _send_instruction(client, token, query, instruction_order, plan_text)

    store = _load_session_store()
    session = _get_or_create_session(store, session_id)
    if session.token_judge and session.token_judge != token:
        session.reset_for_token(token)
    elif not session.token_judge:
        session.token_judge = token
    store[session_id] = session
    _save_session_store(store)

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
            "send_instruction_payload": {"token": token, "jsonData": json_data},
        }
    return result
