from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx


SKILL_NAME = "luanyi_interactive_assistant"
DEFAULT_USER = os.getenv("SKILL_DEFAULT_USER", "skill-client")
HTTP_TIMEOUT = float(os.getenv("SKILL_HTTP_TIMEOUT", "120"))
GREETING_MESSAGE = "您好我是孪易交互助手，正在执行任务，请稍等~"
DEFAULT_LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
DEFAULT_LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-6b59cbb200344af584cff9e66af1f413")
DEFAULT_MCP_BASE_URL = os.getenv("TWINEASY_MCP_BASE_URL", "http://test.twinioc.net/api/editor/mcp").rstrip("/")
DEFAULT_TWINEASY_SERVER_URL = os.getenv("TWINEASY_SERVER_URL", "http://test.twinioc.net/api/editor").rstrip("/")
DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
MCP_AUTH_IN_HEADER = os.getenv("MCP_AUTH_IN_HEADER", "false").lower() == "true"
MAX_HISTORY_ITEMS = 20
MAX_ITERATIONS = 4
STATE_FILE = Path(__file__).resolve().parent.parent / ".runtime" / "session_store.json"


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class SessionState:
    session_id: str
    token_judge: str = ""
    scene_info: str = ""
    history_user: list[dict[str, Any]] = field(default_factory=list)
    history_inter: list[dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def reset_for_token(self, token: str) -> None:
        self.token_judge = token
        self.scene_info = ""
        self.history_user.clear()
        self.history_inter.clear()
        self.updated_at = time.time()


BUILTIN_AGENT_PROMPT = """# 你的目标

你可以精确理解用户的指令意图，并将其转换为系统可执行的标准化指令格式。你可以调用MCP获取额外的信息以辅助理解用户意图，注意mcp接口中所需的token参数为{{#1759562415940.token#}}，当前数字孪生场景的完整配置信息，包括层级结构、业务主题、演示汇报、图层、孪生体类别以及时间轴配置等核心信息从{{#conversation.sceneInfo#}}中获取。
以下是用户提问先从上下文，其中question是用户的提问问题记录，content是返回的指令，从中分析当前场景的层级、状态以及界面信息等，{{#conversation.historyUser#}}；以下是调用MCP接口相关的信息，其中tool_call_name是MCP接口名称，tool_response是接口返回的数据，调用MCP接口前先从调用过的接口中获取，千万不要重复调用，如果没有再调用MCP接口，{{#conversation.historyInter#}}。

## 工作流程
1. 请根据用户的输入内容，智能匹配并直接输出最符合上述指令格式的内容。
2. 若用户输入中包含多个意图，请一次输出多个对应指令。
3. 对于括号中含有“其一”的选项，必须从已知选项中选择最匹配的一个。
4. 对于括号中含有“名称”的选项，首先从MCP接口调用历史中查找，没有再调用MCP接口获取的信息中选择最匹配的一个，如果经过查找仍没有匹配成功，拼接固定语句“场景中没有找到匹配的信息，”以及通过MCP接口查找到的与问题相关的数据信息，然后用一个[]都括起来直接输出，且不用拼接任何指令。
5. 剩下的智能输出所需的内容。
6. 当用户输入“生成XXXX”、“统计XXX”、“创建XXX”、“分析XXX”、“统计一下XXX”等类似表达时，必须识别为“C02：主题生成：XXX”。
7. 当用户输入询问类型的内容时，输出：D01：？，？，？；共X个，其中？代表查询的名称，需要把所有内容输出，然后X是统计的个数。
8. 当用户输入跟聚焦对象和选中对象相关的问题时，对象名称存在时联系询问的上下文：如果是对话开始、没有上下文，输出的指令必须包含“A02：层级切换：（对象所在层级）”；如果该对象与上一个对象操作是同一个层级，并且二者之间没有执行过任何层级切换相关指令（如A02、A03、A04、A05、A06），则只输出对象指令，否则输出必须包含层级切换。
9. 当用户询问有多少对象/孪生体且不带有某个层级时；应该输出所有层级下的孪生体类型以及该类型下的对象名称。
10. 当用户输入问题跟主题切换相关的，如果主题名称存在，输出的指令必须包含“A01：功能切换：分析$C01：主题切换：（主题名称）”。
11. 当用户输入问题跟告警相关时，如看一下告警信息，则输出“A36：告警信息：当前”；如看一下最新的告警，则输出“A36：告警信息：当前&A38：告警信息选中”；如最新的历史告警，则输出“A37：告警信息：历史&A38：告警信息选中”；如果是查看告警触发截图，则输出“A38：告警信息选中&A39：告警截图：打开”。注意根据上下文判断，如果上一个指令包括告警信息选中的指令，则不用重复输出多个指令。
12. 当用户输入问题是打开或关闭XXX灯开关时，对象名称直接从智能开关孪生体中获取，输出“B07：打开灯：（对象名称）”或者“B08：关闭灯：（对象名称）”。

## 特别注意事项
1. 对用户输入进行模糊匹配，例如“园区概览”“园区概况”视为同义。
2. 当用户输入包含多个操作（如“切换到第八层并选中摄像头01”），请分别输出多个指令（如：A02：层级切换：楼层8$B02：选中对象：摄像头01）。
3. 当用户输入“切换主题到园区”“切换到园区主题”“切换园区”等类似表达时，也应识别为“A01：功能切换：分析$C01：主题切换：园区概况”。
4. 对象上卷和对象下钻是不同的指令集，跟层级切换无关。
5. 不需要输出思考过程，不要询问用户任何问题，直接按照输出格式输出你认为正确的结果。

## 指令库
A01：功能切换：？（AI分析、分析、对象、告警、过滤 其一）
A02：层级切换：？（层级名称，必须是从工具接口中返回的内容）
A03：层级切换：下一层
A04：层级切换：上一层
A05：层级切换：第一层
A06：层级切换：最后一层
A07：层级列表：？（打开、关闭 其一）
A08：场景旋转：？（开始、停止 其一）
A09：场景复位
A10：视野放缩：拉近，100
A10：视野放缩：远离，100
A11：视野平移：？（前移、后移、左移、右移 其一），100
A12：视野旋转：？（顺时针、逆时针 其一），10
A13：时间轴：播放
A14：时间轴：暂停
A15：时间轴：跳转到？（时间点或关键锚点）
A16：时间轴：？（回放、实时 其一）
A17：图层管理：？（打开、关闭 其一）
A18：显示图层：？（图层名称，必须是从工具接口中返回的内容）
A19：隐藏图层：？（图层名称，必须是从工具接口中返回的内容）
A20：图层全部显示
A21：图层全部隐藏
A22：图表管理：？（打开、关闭 其一）
A23：显示图表：？（图表名称，必须是从工具接口中返回的内容）
A24：关闭图表：？（图表名称，必须是从工具接口中返回的内容）
A25：环境控制：？（打开、关闭 其一）
A26：时间切换：？（具体时间点）
A27：季节切换：？（春季、夏季、秋季、冬季 其一）
A28：天气切换：？（晴、晴间多云、阴天、小雨、中雨、大雨、小雪、中雪、大雪、雾、霾、扬沙 其一）
A29：演示汇报：？（打开、关闭 其一）
A30：开始演示：？（演示汇报名称，必须是从工具接口中返回的内容）
A31：停止演示
A32：暂停演示
A33：上一步演示
A34：下一步演示
A35：重新演示
A36：告警信息：当前
A37：告警信息：历史
A38：告警信息选中
A39：告警截图：（打开、关闭 其一）
B01：聚焦对象：？（对象名称，必须是从工具接口中返回的内容）
B02：选中对象：？（对象名称，必须是从工具接口中返回的内容）
B03：取消选中
B04：对象下钻
B05：对象上卷
B06：搜索对象：？（搜索内容）
B07：打开灯：？（对象名称，必须是从工具接口中返回的内容）
B08：关闭灯：？（对象名称，必须是从工具接口中返回的内容）
C01：主题切换：？（主题名称，必须是从工具接口中返回的内容）
C02：主题生成：？（生成的内容）
D01：？，？，？；共X个（询问类内容）

## 输出格式
[指令1$指令2$指令3$...]

## 输出示例
1. 示例1：用户有两个意图，并且对应指令和参数：[A02：层级切换：楼层8$B02：选中对象：摄像头01]
2. 示例2：用户只有一个意图：[A04：层级切换：上一层]
3. 示例3：用户有多个询问类意图：[D01：摄像头01，摄像头02，摄像头03；共3个$D01：告警01，告警02；共2个]
4. 示例4：选中摄像头01：[A02：层级切换：层级2$B02：选中对象：摄像头01]
"""

BUILTIN_TOOLS = {
    "get_scene_info": ToolSpec(
        name="get_scene_info",
        description="获取当前数字孪生场景的完整配置信息，包括层级名称、业务主题、演示汇报、图层、孪生体类别以及时间轴信息。",
        parameters={
            "type": "object",
            "properties": {"token": {"type": "string", "description": "场景 token"}},
            "required": ["token"],
            "additionalProperties": False,
        },
    ),
    "get_twin_category": ToolSpec(
        name="get_twin_category",
        description="根据层级名称获取该层级下存在的所有孪生体类别名称列表。",
        parameters={
            "type": "object",
            "properties": {
                "levelName": {"type": "string", "description": "层级名称，例如 1F、2F、B1"},
                "token": {"type": "string", "description": "场景 token"},
            },
            "required": ["levelName", "token"],
            "additionalProperties": False,
        },
    ),
    "get_charts": ToolSpec(
        name="get_charts",
        description="获取当前数字孪生场景中配置的所有图表名称列表。",
        parameters={
            "type": "object",
            "properties": {"token": {"type": "string", "description": "场景 token"}},
            "required": ["token"],
            "additionalProperties": False,
        },
    ),
    "get_twin_category_data": ToolSpec(
        name="get_twin_category_data",
        description="根据孪生体类别名称获取该类别下的所有孪生体实例名称列表。",
        parameters={
            "type": "object",
            "properties": {
                "twinCategoryName": {"type": "string", "description": "孪生体类别名称"},
                "token": {"type": "string", "description": "场景 token"},
            },
            "required": ["twinCategoryName", "token"],
            "additionalProperties": False,
        },
    ),
}

NO_ARG_COMMAND_TEXT = {
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
}

DIRECT_INFO_PREFIXES = {
    "A01", "A02", "A07", "A08", "A10", "A11", "A12", "A15", "A16", "A17", "A18",
    "A19", "A22", "A23", "A24", "A25", "A29", "A39", "B01", "B02", "B06", "B07",
    "B08", "C01", "C02",
}
ENVIRONMENT_PREFIXES = {"A26", "A27", "A28"}
DEMO_PREFIXES = {"A30"}


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
            history_user=list(payload.get("history_user", []) or []),
            history_inter=list(payload.get("history_inter", []) or []),
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
    replacements = {
        "{{#1759562415940.token#}}": token,
        "{{#conversation.sceneInfo#}}": _render_context_value(session.scene_info),
        "{{#conversation.historyUser#}}": _render_context_value(session.history_user),
        "{{#conversation.historyInter#}}": _render_context_value(session.history_inter),
    }
    for placeholder, actual in replacements.items():
        prompt = prompt.replace(placeholder, actual)
    return prompt


def _get_llm_headers() -> dict[str, str]:
    if not DEFAULT_LLM_API_KEY:
        raise SkillRuntimeError("缺少 LLM_API_KEY")
    return {
        "Authorization": f"Bearer {DEFAULT_LLM_API_KEY}",
        "Content-Type": "application/json",
    }


def _get_mcp_headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token and MCP_AUTH_IN_HEADER:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _invoke_mcp_tool(client: httpx.AsyncClient, tool_name: str, arguments: dict[str, Any], token: str) -> Any:
    direct_url = f"{DEFAULT_MCP_BASE_URL}/{tool_name}"
    wrapped_payload = {"tool_name": tool_name, "arguments": arguments}
    headers = _get_mcp_headers(token)

    response = await client.post(direct_url, headers=headers, json=arguments)
    if response.status_code in {404, 405}:
        response = await client.post(DEFAULT_MCP_BASE_URL, headers=headers, json=wrapped_payload)

    if response.status_code >= 400:
        response_text = response.text.strip()
        raise SkillRuntimeError(
            f"MCP 工具调用失败({tool_name}) status={response.status_code} url={response.request.url} body={response_text}"
        )

    json_data = _safe_json_loads(response.text)
    return json_data if json_data is not None else response.text


async def _fetch_scene_info(client: httpx.AsyncClient, token: str) -> Any:
    return await _invoke_mcp_tool(client, "get_scene_info", {"token": token}, token)


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


async def _run_agent(client: httpx.AsyncClient, query: str, token: str, session: SessionState, llm_model: str) -> tuple[str, list[dict[str, Any]]]:
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
                    tool_result = await _invoke_mcp_tool(client, tool_name, arguments, token)
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


def _extract_last_bracket_raw_content(text: str) -> str:
    last_close_idx = text.rfind("]")
    if last_close_idx == -1:
        return ""
    last_open_idx = text.rfind("[", 0, last_close_idx)
    if last_open_idx == -1:
        return ""
    return text[last_open_idx + 1:last_close_idx].strip()


def _extract_info(command: str) -> str:
    parts = command.split("：", 1)
    if len(parts) > 1:
        return parts[1].strip()
    return command.strip() if command else ""


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


def _get_display_text(command: str) -> str:
    command_prefix = _get_command_prefix(command)
    if command_prefix in NO_ARG_COMMAND_TEXT:
        return NO_ARG_COMMAND_TEXT[command_prefix]
    normalized_command = _normalize_command_token(command)
    if "：" not in command:
        return "执行失败，失败原因：" + normalized_command
    extracted = _extract_info(command)
    if command_prefix in DIRECT_INFO_PREFIXES:
        return extracted
    if command_prefix in ENVIRONMENT_PREFIXES:
        return "环境控制" + extracted
    if command_prefix in DEMO_PREFIXES:
        return "演示汇报" + extracted
    return "执行失败，失败原因：" + command


def _process_single_command(command: str) -> str:
    if command.startswith("D"):
        if "：" in command:
            return f"为您查找到相关内容如下：{command.split('：', 1)[1].strip()}"
        if len(command) >= 4:
            return f"为您查找到相关内容如下：{command[3:]}"
        return "执行失败，字符串长度不足"
    return _get_display_text(command)


def _build_execution_plan(agent_text: str) -> tuple[str, str]:
    raw_instruction_order = _extract_last_bracket_content(agent_text)
    raw_commands = raw_instruction_order.strip().split("$") if raw_instruction_order.strip() else []
    normalized_commands = [_normalize_instruction_command(command) for command in raw_commands if command.strip()]
    instruction_order = "$".join(command.strip() for command in raw_commands if command.strip())
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
        if normalized_commands and normalized_commands[0].strip().startswith("D"):
            first_result = results[0]
            final_result = first_result.split("、", 1)[1] if "、" in first_result else first_result
        else:
            final_result = "根据最优策略，已经为您规划如下执行计划：\n" + "\n".join(results)
    else:
        final_result = "未识别出有效指令，请先查询场景有哪些内容再查找"
    return final_result, instruction_order


def _build_raw_answer(plan_text: str) -> str:
    greeting = '{\n"response": "' + GREETING_MESSAGE.replace('"', '\\"') + '"\n}'
    plan = '{\n"response": "' + plan_text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"\n}'
    return f"{greeting}THISSECTIONEND{plan}THISSECTIONEND\nAGENTEND"


def _build_response_content(plan_text: str) -> str:
    greeting = '{\n"response": "' + GREETING_MESSAGE.replace('"', '\\"') + '"\n}'
    plan = '{\n"response": "' + plan_text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"\n}'
    return f"{greeting}THISSECTIONEND{plan}THISSECTIONEND"


def _build_json_data(query: str, instruction_order: str, plan_text: str) -> str:
    return f"{instruction_order}$&{query}$&{plan_text}"


async def _send_instruction(client: httpx.AsyncClient, token: str, query: str, instruction_order: str, plan_text: str) -> Any:
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


def _append_history(session: SessionState, query: str, agent_text: str, tool_calls: list[dict[str, Any]]) -> None:
    if tool_calls:
        simplified_tool_records = [
            {
                "tool_call_name": item.get("tool_call_name"),
                "tool_response": item.get("tool_response"),
            }
            for item in tool_calls
        ]
        session.history_inter.extend(simplified_tool_records)
        session.history_inter = session.history_inter[-MAX_HISTORY_ITEMS:]
    session.history_user.append({"question": query, "content": _extract_last_bracket_raw_content(agent_text)})
    session.history_user = session.history_user[-MAX_HISTORY_ITEMS:]
    session.updated_at = time.time()


async def invoke_skill(
    query: str,
    token: str,
    session_id: str | None = None,
    execute_instruction: bool = True,
    debug: bool = False,
    llm_model: str | None = None,
) -> dict[str, Any]:
    if not query:
        raise SkillRuntimeError("query 不能为空")
    if not token:
        raise SkillRuntimeError("token 不能为空")

    session_key = session_id or token
    store = _load_session_store()
    session = _get_or_create_session(store, session_key)
    scene_info_error: str | None = None
    if session.token_judge and session.token_judge != token:
        session.reset_for_token(token)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            if not session.scene_info or session.token_judge != token:
                try:
                    scene_info_raw = await _fetch_scene_info(client, token)
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
                session.history_user = []
                session.history_inter = []

            agent_text, tool_calls = await _run_agent(client, query, token, session, llm_model or DEFAULT_LLM_MODEL)
            plan_text, instruction_order = _build_execution_plan(agent_text)
            json_data = _build_json_data(query, instruction_order, plan_text)
            response_content = _build_response_content(plan_text)

            execution_result: Any = None
            if execute_instruction and instruction_order:
                execution_result = await _send_instruction(client, token, query, instruction_order, plan_text)

            _append_history(session, query, agent_text, tool_calls)
            store[session_key] = session
            _save_session_store(store)

            result = {
                "jsonData": json_data,
                "response": response_content,
            }
            if execute_instruction:
                result["execution_result"] = execution_result
            if debug:
                result["debug_info"] = {
                    "agent_raw_output": agent_text,
                    "instruction_order": instruction_order,
                    "send_instruction_payload": {
                        "token": token,
                        "jsonData": json_data,
                    },
                    "scene_info": session.scene_info,
                    "scene_info_error": scene_info_error,
                    "session_state": {
                        "token_judge": session.token_judge,
                        "history_user_count": len(session.history_user),
                        "history_inter_count": len(session.history_inter),
                    },
                    "raw_answer": _build_raw_answer(plan_text),
                    "tool_calls": tool_calls,
                }
            return result
    except httpx.TimeoutException as exc:
        raise SkillRuntimeError(f"上游请求超时: {exc}") from exc
    except httpx.HTTPError as exc:
        raise SkillRuntimeError(f"上游请求失败: {exc}") from exc
