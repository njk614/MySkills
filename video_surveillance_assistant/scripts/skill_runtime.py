from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from itertools import count
from pathlib import Path
from typing import Any

import httpx


SKILL_NAME = "video_surveillance_assistant"
DEFAULT_USER = os.getenv("SKILL_DEFAULT_USER", "skill-client")
HTTP_TIMEOUT = float(os.getenv("SKILL_HTTP_TIMEOUT", "120"))
GREETING_MESSAGE = "您好我是视频监控助手，正在执行任务，请稍等~"
DEFAULT_LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
DEFAULT_LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-6b59cbb200344af584cff9e66af1f413")
DEFAULT_MCP_BASE_URL = os.getenv("TWINEASY_MCP_BASE_URL", "http://test.twinioc.net/api/editor/mcp").rstrip("/")
DEFAULT_TWINEASY_SERVER_URL = os.getenv("TWINEASY_SERVER_URL", "http://test.twinioc.net/api/editor").rstrip("/")
DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
MCP_AUTH_IN_HEADER = os.getenv("MCP_AUTH_IN_HEADER", "false").lower() == "true"
MCP_PROTOCOL_VERSION = os.getenv("MCP_PROTOCOL_VERSION", "2025-03-26")
MAX_HISTORY_ITEMS = 20
MAX_ITERATIONS = 4
STATE_FILE = Path(__file__).resolve().parent.parent / ".runtime" / "session_store.json"
JSON_RPC_ID_COUNTER = count(1)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class SessionState:
    session_id: str
    token_judge: str = ""
    history_user: list[dict[str, Any]] = field(default_factory=list)
    history_inter: list[dict[str, Any]] = field(default_factory=list)
    mcp_session_id: str = ""
    mcp_initialized: bool = False
    updated_at: float = field(default_factory=time.time)

    def reset_for_token(self, token: str) -> None:
        self.token_judge = token
        self.history_user.clear()
        self.history_inter.clear()
        self.mcp_session_id = ""
        self.mcp_initialized = False
        self.updated_at = time.time()


BUILTIN_AGENT_PROMPT = """# 你的目标

你可以精确理解用户的指令意图，并将其转换为系统可执行的标准化指令格式。你可以调用MCP获取额外的信息以辅助理解用户意图，注意：mcp接口中所需的token参数为{token}；只有涉及到对象名称或摄像头名称的相关指令需要调用mcp接口，其他的不用；用户提问先从上下文{historyUser}中分析当前场景摄像头的信息，如果是以前问过的问题直接返回，如果不是继续分析；调用MCP接口前应先从{historyInter}获取中获取相关的信息，如果有直接分析返回，如果没有再调用MCP接口

## 工作流程

1. 请根据用户的输入内容，智能匹配并直接输出最符合上述指令格式的内容。
2. 若用户输入中包含多个意图，请一次输出多个对应指令。
3. 对于括号中含有"其一"的选项，必须从已知选项中选择最匹配的一个。
4. 对于括号中含有"摄像头名称"的选项，必须从调用MCP获取的信息中选择最匹配的一个，如果没有匹配成功，直接输出"[视频中没有找到匹配的信息]"且不用拼接任何指令，非常重要优先级最高。
5. 当用户问题是关于查看某个对象（摄像头）或查看某个对象（摄像头）详情时，直接输出"E34：筛选：摄像头名称"
6. 当用户问题是某个对象（摄像头）放大或缩小时，直接输出"E34：筛选：摄像头名称$E32/E33单路云台：拉近/拉远"；当用户问题只有放大、缩小、拉近、拉远、左右上下旋转、抬头、低头时，直接输出单路指令相关的指令
7. 当用户问题是某个对象（摄像头）的告警信息或事件信息时，直接输出"E34：筛选：摄像头名称$E12：事件：事件列表，选中"
8. 当用户问题是询问类的问题时，比如可控摄像头有哪些或大华摄像头有什么时，查找MCP接口中相关的描述信息，符合要求的对象名称全部输出"E35：名称：（对象名称，中间用，分割）"
9. 确保准确区分"视频下一页/上一页"（E05/E06）和"下一个/上一个视频"（E08/E09）的不同指令。
10. 用户问题是关于告警时，返回的是事件相关指令，此处告警相当于事件，如用户问题是看一下告警信息，则输出"E12：事件：事件列表，选中"
11. 当用户问题和指令库中的指令都不匹配时，直接输出："您的提问超出了我能回答的范围，请输出跟视频监控相关的问题！"

## 指令库

E01：筛选：范围选取：中心点，？；范围，？
E02：筛选：设置显示模式，？（单路、2×2、3×3 其一）
E03：视频：轮播视频，？（开始、停止 其一）
E04：视频：视频排序，？（按对象名称正序、按对象名称倒序、按创建时间正序、按创建时间倒序 其一）
E05：视频：视频上一页
E06：视频：视频下一页
E07：视频：视频指定页，？
E08：视频：下一个视频
E09：视频：上一个视频
E10：视频：第一个视频
E11：视频：末一个视频
E12：事件：事件列表，？（选中、取消 其一）
E13：事件：轮播事件，？（开始、停止 其一）
E14：事件：事件筛选，？
E15：事件：事件排序，？（按时间正序、按时间倒序 其一）
E16：事件：选中事件，？
E17：事件：下一个事件
E18：事件：上一个事件
E19：事件：第一个事件
E20：事件：末一个事件
E21：时间：模式切换，（实时、回放 其一）
E22：回放：暂停
E23：回放：播放
E24：回放：跳转，？
E25：回放：前进，？
E26：回放：回退，？
E27：回放：倍速，？
E28：单路云台：左转
E29：单路云台：右转
E30：单路云台：抬头
E31：单路云台：低头
E32：单路云台：拉近
E33：单路云台：拉远
E34：筛选：？（摄像头名称，从MCP接口中获取）
E35：名称：？，？，？...（摄像头名称，从MCP接口中获取）

## 输出格式

[指令1$指令2$指令3$...]

## 输出示例

1. 示例1: 用户输入"下一个视频"
[E08：视频：下一个视频]

2. 示例2: 用户输入"显示模式设置为3x3"
[E02：筛选：设置显示模式，3×3]

3. 示例3: 用户输入"云台右转"
[E29：单路云台：右转]

4. 示例4: 用户输入"查看1号摄像头"
[E34：筛选：1号摄像头]

5. 示例5: 用户输入"可控摄像头有哪些"
[E35：名称：1号摄像头，大门监控，车间探头]

## 特别注意事项

1. 不需要输出思考过程，不要询问用户任何问题，直接按照输出格式输出你认为正确的结果
"""

BUILTIN_TOOLS = {
    "get_bind_video_instance_names": ToolSpec(
        name="get_bind_video_instance_names",
        description=(
            "获取当前数字孪生场景中所有已绑定视频源的孪生体实例信息列表。"
            "功能说明：查询场景中类别名称包含'视频'、'摄像头'、'探头'关键字的孪生体，"
            "筛选出已绑定视频服务器的实例，返回其实例名称和描述信息。"
            "仅返回状态为'可用'的孪生体类别配置下的实例。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "SignalR连接时返回的6位UniqueId",
                }
            },
            "required": ["token"],
            "additionalProperties": False,
        },
    ),
}

# 无参数固定指令的中文展示映射
NO_ARG_COMMAND_TEXT: dict[str, str] = {
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

# 带参数指令：去掉编码后直接使用冒号后的内容作为展示文本
DIRECT_INFO_PREFIXES = {
    "E01", "E02", "E03", "E04", "E07",
    "E12", "E13", "E14", "E15", "E16",
    "E21", "E24", "E25", "E26", "E27",
    "E34",
}


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
            history_user=list(payload.get("history_user", []) or []),
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


def _render_context_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value or "")


def _render_agent_prompt(session: SessionState, token: str) -> str:
    prompt = BUILTIN_AGENT_PROMPT
    prompt = prompt.replace("{token}", token)
    prompt = prompt.replace("{historyUser}", _render_context_value(session.history_user))
    prompt = prompt.replace("{historyInter}", _render_context_value(session.history_inter))
    return prompt


def _get_llm_headers() -> dict[str, str]:
    if not DEFAULT_LLM_API_KEY:
        raise SkillRuntimeError("缺少 LLM_API_KEY，请设置环境变量 LLM_API_KEY")
    return {
        "Authorization": f"Bearer {DEFAULT_LLM_API_KEY}",
        "Content-Type": "application/json",
    }


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
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
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
            "clientInfo": {
                "name": SKILL_NAME,
                "version": "1.0.0",
            },
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
            params={
                "name": tool_name,
                "arguments": arguments,
            },
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
                params={
                    "name": tool_name,
                    "arguments": arguments,
                },
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


async def _call_llm(client: httpx.AsyncClient, messages: list[dict[str, Any]], model_name: str) -> dict[str, Any]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in BUILTIN_TOOLS.values()
    ]

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.1,
        "tools": tools,
        "tool_choice": "auto",
    }

    response = await client.post(
        f"{DEFAULT_LLM_BASE_URL}/chat/completions",
        headers=_get_llm_headers(),
        json=payload,
    )
    if response.status_code >= 400:
        raise SkillRuntimeError(f"LLM 调用失败: {response.text}")

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise SkillRuntimeError("LLM 未返回有效结果")
    return choices[0].get("message") or {}


async def _run_agent(
    client: httpx.AsyncClient,
    query: str,
    token: str,
    session: SessionState,
    llm_model: str,
) -> tuple[str, list[dict[str, Any]]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _render_agent_prompt(session, token)},
        {"role": "user", "content": query},
    ]
    tool_call_records: list[dict[str, Any]] = []

    for _ in range(MAX_ITERATIONS):
        message = await _call_llm(client, messages, llm_model)
        tool_calls = message.get("tool_calls") or []
        content = (message.get("content") or "").strip()

        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            for tool_call in tool_calls:
                function_meta = tool_call.get("function") or {}
                tool_name = function_meta.get("name")
                if not tool_name:
                    raise SkillRuntimeError("LLM 返回了缺少名称的工具调用")
                raw_arguments = function_meta.get("arguments") or "{}"
                arguments = raw_arguments if isinstance(raw_arguments, dict) else (_safe_json_loads(raw_arguments) or {})
                if "token" not in arguments:
                    arguments["token"] = token
                try:
                    tool_result = await _invoke_mcp_tool(client, session, tool_name, arguments, token)
                except SkillRuntimeError as exc:
                    tool_result = {
                        "success": False,
                        "tool_name": tool_name,
                        "error": str(exc),
                        "fallback": True,
                    }
                record = {
                    "tool_call_name": tool_name,
                    "tool_arguments": arguments,
                    "tool_response": tool_result,
                }
                tool_call_records.append(record)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": tool_name,
                        "content": _stringify(tool_result),
                    }
                )
            continue

        if content:
            return content, tool_call_records

    raise SkillRuntimeError("Agent 达到最大迭代次数后仍未生成有效指令")


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


def _extract_info(command: str) -> str:
    parts = command.split("：", 1)
    if len(parts) > 1:
        return parts[1].strip()
    return command.strip() if command else ""


def _normalize_command_token(command: str) -> str:
    return str(command or "").strip().upper().rstrip("：:")


def _get_command_prefix(command: str) -> str:
    token = _normalize_command_token(command)
    # E 系列编码格式：E + 两位数字，如 E01, E34
    if len(token) >= 3 and token[0] == "E" and token[1:3].isdigit():
        return token[:3]
    return token[:3]


def _normalize_instruction_command(command: str) -> str:
    stripped = str(command or "").strip()
    if not stripped:
        return ""
    command_prefix = _get_command_prefix(stripped)
    if command_prefix in NO_ARG_COMMAND_TEXT:
        return command_prefix
    return stripped


def _get_display_text(command: str) -> str:
    command_prefix = _get_command_prefix(command)
    if command_prefix in NO_ARG_COMMAND_TEXT:
        return NO_ARG_COMMAND_TEXT[command_prefix]
    if "：" not in command:
        return "执行失败，失败原因：" + _normalize_command_token(command)
    extracted = _extract_info(command)
    if command_prefix in DIRECT_INFO_PREFIXES:
        return extracted
    return "执行失败，失败原因：" + command


def _process_single_command(command: str) -> str:
    command_prefix = _get_command_prefix(command)
    # E35 为查询类指令：输出名称列表
    if command_prefix == "E35":
        if "：" in command:
            names_part = command.split("：", 1)[1].strip()
            # 去掉前导"名称："前缀（如有）
            if names_part.startswith("名称："):
                names_part = names_part[3:].strip()
            names = [n.strip() for n in names_part.split("，") if n.strip()]
            count = len(names)
            return f"为您查找到相关内容如下：{'、'.join(names)}；共{count}个"
        return "为您查找到相关内容如下：（无数据）"
    return _get_display_text(command)


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
        # E35 查询类单指令不加"规划执行计划"前缀
        if normalized_commands and _get_command_prefix(normalized_commands[0].strip()) == "E35":
            first_result = results[0]
            final_result = first_result.split("、", 1)[1] if "、" in first_result else first_result
        else:
            final_result = "根据最优策略，已经为您规划如下执行计划：\n" + "\n".join(results)
    else:
        final_result = "目前无法回答与提问相关的问题，请咨询跟视频相关的问题"

    return final_result, instruction_order


def _build_raw_answer(plan_text: str) -> str:
    greeting = '{\n"response": "' + GREETING_MESSAGE.replace('"', '\\"') + '"\n}'
    plan = '{\n"response": "' + plan_text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"\n}'
    return f"{greeting}THISSECTIONEND{plan}THISSECTIONEND\nAGENTEND"


def _build_response_content(plan_text: str) -> str:
    greeting = '{\n"response": "' + GREETING_MESSAGE.replace('"', '\\"') + '"\n}'
    plan = '{\n"response": "' + plan_text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"\n}'
    return f"{greeting}THISSECTIONEND{plan}THISSECTIONEND"


def _build_json_data(query: str, instruction_order: str, plan_text: str) -> str:
    return f"{instruction_order}$&{query}$&{plan_text}"


async def _send_instruction(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    instruction_order: str,
    plan_text: str,
) -> Any:
    json_data = _build_json_data(query, instruction_order, plan_text)
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


def _append_history(
    session: SessionState,
    query: str,
    agent_text: str,
    tool_calls: list[dict[str, Any]],
) -> None:
    raw_bracket = _extract_last_bracket_content(agent_text)
    user_record = {
        "question": query,
        "content": raw_bracket,
    }
    session.history_user.append(user_record)
    if len(session.history_user) > MAX_HISTORY_ITEMS:
        session.history_user = session.history_user[-MAX_HISTORY_ITEMS:]

    if tool_calls:
        simplified_tool_records = [
            {
                "tool_call_name": item.get("tool_call_name"),
                "tool_response": item.get("tool_response"),
            }
            for item in tool_calls
        ]
        session.history_inter.extend(simplified_tool_records)
        if len(session.history_inter) > MAX_HISTORY_ITEMS:
            session.history_inter = session.history_inter[-MAX_HISTORY_ITEMS:]

    session.updated_at = time.time()


async def invoke_skill(
    query: str,
    token: str,
    session_id: str = "default",
    execute_instruction: bool = True,
    debug: bool = False,
    llm_model: str | None = None,
) -> dict[str, Any]:
    model_name = llm_model or DEFAULT_LLM_MODEL
    store = _load_session_store()
    session = _get_or_create_session(store, session_id)

    # token 变更时重置会话
    if session.token_judge and session.token_judge != token:
        session.reset_for_token(token)
    elif not session.token_judge:
        session.token_judge = token

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        agent_text, tool_calls = await _run_agent(client, query, token, session, model_name)

        if debug:
            print(f"[DEBUG] agent_text: {agent_text}")
            print(f"[DEBUG] tool_calls: {json.dumps(tool_calls, ensure_ascii=False, indent=2)}")

        plan_text, instruction_order = _build_execution_plan(agent_text)
        _append_history(session, query, agent_text, tool_calls)
        _save_session_store(store)

        send_result = None
        if execute_instruction and instruction_order:
            send_result = await _send_instruction(client, token, query, instruction_order, plan_text)

    raw_answer = _build_raw_answer(plan_text)
    return {
        "skill_name": SKILL_NAME,
        "success": True,
        "query": query,
        "agent_text": agent_text,
        "instruction_order": instruction_order,
        "plan_text": plan_text,
        "raw_answer": raw_answer,
        "send_result": send_result,
    }
