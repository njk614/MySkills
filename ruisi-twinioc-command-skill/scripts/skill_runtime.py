from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from itertools import count
from pathlib import Path
from typing import Any

import httpx


SKILL_NAME = "ruisi_twinioc_command_executor"
HTTP_TIMEOUT = float(os.getenv("SKILL_HTTP_TIMEOUT", "120"))
DEFAULT_TWINEASY_BASE_URL = os.getenv("TWINEASY_BASE_URL", "http://test.twinioc.net").rstrip("/")
DEFAULT_MCP_BASE_URL = os.getenv("TWINEASY_MCP_BASE_URL", f"{DEFAULT_TWINEASY_BASE_URL}/api/editor/mcp").rstrip("/")
DEFAULT_TWINEASY_SERVER_URL = os.getenv("TWINEASY_SERVER_URL", f"{DEFAULT_TWINEASY_BASE_URL}/api/editor").rstrip("/")
MCP_AUTH_IN_HEADER = os.getenv("MCP_AUTH_IN_HEADER", "false").lower() == "true"
MCP_PROTOCOL_VERSION = os.getenv("MCP_PROTOCOL_VERSION", "2025-03-26")
MAX_HISTORY_ITEMS = 20
# session 缓存统一存放在 ruisi-twinioc-dataquery-skill 中
_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = _SKILLS_ROOT / "ruisi-twinioc-dataquery-skill" / ".runtime" / "session_store.json"
JSON_RPC_ID_COUNTER = count(1)
BACKGROUND_SEND_DELAY_SECONDS = float(os.getenv("SEND_INSTRUCTION_DELAY_SECONDS", "2"))
ENTITY_ALIAS_FILE = _SKILLS_ROOT / "ruisi-twinioc-dataquery-skill" / "entity_aliases.json"


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

EN_NO_ARG_COMMAND_TEXT: dict[str, str] = {
    "A03": "Level switch: next level",
    "A04": "Level switch: previous level",
    "A05": "Level switch: first level",
    "A06": "Level switch: last level",
    "A09": "Reset the scene",
    "A13": "Timeline: play",
    "A14": "Timeline: pause",
    "A20": "Show all layers",
    "A21": "Hide all layers",
    "A31": "Stop presentation",
    "A32": "Pause presentation",
    "A33": "Previous presentation step",
    "A34": "Next presentation step",
    "A35": "Restart presentation",
    "A36": "Alarm info: current",
    "A37": "Alarm info: history",
    "A38": "Select alarm info",
    "B03": "Clear selection",
    "B04": "Drill down object",
    "B05": "Drill up object",
    "E05": "Video: previous page",
    "E06": "Video: next page",
    "E08": "Video: next video",
    "E09": "Video: previous video",
    "E10": "Video: first video",
    "E11": "Video: last video",
    "E17": "Event: next event",
    "E18": "Event: previous event",
    "E19": "Event: first event",
    "E20": "Event: last event",
    "E22": "Playback: pause",
    "E23": "Playback: play",
    "E28": "PTZ: pan left",
    "E29": "PTZ: pan right",
    "E30": "PTZ: tilt up",
    "E31": "PTZ: tilt down",
    "E32": "PTZ: zoom in",
    "E33": "PTZ: zoom out",
}

PLAN_MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "query_result_prefix": "为您查找到相关内容如下：",
        "camera_names_prefix": "为您查找到相关内容如下：{names}；共{count}个",
        "failure_prefix": "执行失败，失败原因：",
        "presentation_prefix": "演示汇报",
        "plan_header": "根据最优策略，已经为您规划如下执行计划：\n",
        "no_instruction": "未识别出有效指令，请先查询场景有哪些内容再查找",
        "queued_message": "指令已进入后台发送队列，OpenClaw 返回不再等待孪易 HTTP 响应",
    },
    "en-US": {
        "query_result_prefix": "Here is the information I found: ",
        "camera_names_prefix": "Here are the camera names: {names}; total {count}",
        "failure_prefix": "Execution failed: ",
        "presentation_prefix": "Presentation: ",
        "plan_header": "Based on the optimal strategy, I have prepared the following execution plan:\n",
        "no_instruction": "No valid instruction was recognized. Please query the scene contents first.",
        "queued_message": "The instruction has been queued for background delivery. OpenClaw no longer waits for the TwinIOC HTTP response.",
    },
}

EN_TEXT_REPLACEMENTS: list[tuple[str, str]] = [
    ("告警信息选中", "Select alarm info"),
    ("打开温控器", "Turn on the air conditioner"),
    ("关闭温控器", "Turn off the air conditioner"),
    ("打开照明灯", "Turn on the lights"),
    ("关闭照明灯", "Turn off the lights"),
    ("照明灯开关", "light switch"),
    ("灯开关", "light switch"),
    ("照明灯", "lights"),
    ("聚焦对象", "Focus on"),
    ("对象下钻", "Drill down object"),
    ("对象上卷", "Drill up object"),
    ("取消选中", "Clear selection"),
    ("选中", "select"),
    ("选中对象", "Select object"),
    ("对象选中", "Select object"),
    ("图层管理", "Layer management"),
    ("图表管理", "Chart management"),
    ("环境控制", "Environment control"),
    ("演示汇报", "Presentation report"),
    ("告警截图", "Alarm screenshot"),
    ("告警", "alarm"),
    ("层级列表", "Level list"),
    ("时间轴", "Timeline"),
    ("时间切换", "Time switch"),
    ("季节切换", "Season switch"),
    ("天气切换", "Weather switch"),
    ("主题切换", "Theme switch"),
    ("主题生成", "Theme generation"),
    ("场景复位", "Reset the scene"),
    ("场景旋转", "Scene rotation"),
    ("功能切换", "Function switch"),
    ("显示图层", "Show layer"),
    ("隐藏图层", "Hide layer"),
    ("显示图表", "Show chart"),
    ("关闭图表", "Close chart"),
    ("告警信息", "Alarm info"),
    ("单路云台", "PTZ"),
    ("设置显示模式", "set display mode"),
    ("视频上一页", "previous video page"),
    ("视频下一页", "next video page"),
    ("上一个视频", "previous video"),
    ("下一个视频", "next video"),
    ("第一个视频", "first video"),
    ("末一个视频", "last video"),
    ("轮播视频", "video carousel"),
    ("视频排序", "video sort"),
    ("上一个事件", "previous event"),
    ("下一个事件", "next event"),
    ("第一个事件", "first event"),
    ("末一个事件", "last event"),
    ("事件列表", "event list"),
    ("轮播事件", "event carousel"),
    ("事件排序", "event sort"),
    ("模式切换", "mode switch"),
    ("打开灯", "Turn on the lights"),
    ("关闭灯", "Turn off the lights"),
    ("层级切换", "Level switch"),
    ("打开", "open"),
    ("关闭", "close"),
    ("取消", "cancel"),
    ("对象", "object"),
    ("过滤", "filter"),
    ("筛选", "Filter"),
    ("视频", "Video"),
    ("事件", "Event"),
    ("时间", "Time"),
    ("回放", "Playback"),
    ("图层", "Layer"),
    ("图表", "Chart"),
    ("单路", "single"),
    ("中心点", "center point"),
    ("范围", "range"),
    ("下一层", "next level"),
    ("上一层", "previous level"),
    ("第一层", "first level"),
    ("最后一层", "last level"),
    ("开始", "start"),
    ("停止", "stop"),
    ("暂停", "pause"),
    ("播放", "play"),
    ("顺时针", "clockwise"),
    ("逆时针", "counterclockwise"),
    ("前移", "move forward"),
    ("后移", "move backward"),
    ("左移", "move left"),
    ("右移", "move right"),
    ("左转", "pan left"),
    ("右转", "pan right"),
    ("抬头", "tilt up"),
    ("低头", "tilt down"),
    ("拉近", "zoom in"),
    ("拉远", "zoom out"),
    ("实时", "real-time"),
    ("历史", "history"),
    ("当前", "current"),
    ("分析", "analysis"),
    ("AI分析", "AI analysis"),
    ("对象名称正序", "object name ascending"),
    ("对象名称倒序", "object name descending"),
    ("创建时间正序", "creation time ascending"),
    ("创建时间倒序", "creation time descending"),
    ("按对象名称正序", "by object name ascending"),
    ("按对象名称倒序", "by object name descending"),
    ("按创建时间正序", "by creation time ascending"),
    ("按创建时间倒序", "by creation time descending"),
    ("按时间正序", "by time ascending"),
    ("按时间倒序", "by time descending"),
    ("春季", "spring"),
    ("夏季", "summer"),
    ("秋季", "autumn"),
    ("冬季", "winter"),
    ("晴间多云", "partly cloudy"),
    ("阴天", "cloudy"),
    ("小雨", "light rain"),
    ("中雨", "moderate rain"),
    ("大雨", "heavy rain"),
    ("小雪", "light snow"),
    ("中雪", "moderate snow"),
    ("大雪", "heavy snow"),
    ("扬沙", "sand"),
    ("晴", "sunny"),
    ("雾", "fog"),
    ("霾", "haze"),
    ("园区概况", "campus overview"),
    ("资产盘点", "Asset inventory"),
    ("显隐路径", "Show/hide path"),
]

EN_TEXT_BOUNDARY_PHRASES: tuple[str, ...] = (
    "light switch",
    "the lights",
    "air conditioner",
    "turn on",
    "turn off",
    "focus on",
    "drill down object",
    "drill up object",
    "clear selection",
    "select object",
    "layer management",
    "chart management",
    "environment control",
    "presentation report",
    "alarm info",
    "scene rotation",
    "function switch",
    "show layer",
    "hide layer",
    "show chart",
    "close chart",
    "video",
    "event",
    "playback",
    "timeline",
    "PTZ",
)

EN_TO_ZH_FIXED_REPLACEMENTS: list[tuple[str, str]] = sorted(
    [
        *( (target, source) for source, target in EN_TEXT_REPLACEMENTS ),
        ("AI analysis", "AI分析"),
        ("Timeline", "时间轴"),
        ("Level list", "层级列表"),
        ("Layer management", "图层管理"),
        ("Chart management", "图表管理"),
        ("Environment control", "环境控制"),
        ("Season switch", "季节切换"),
        ("Weather switch", "天气切换"),
        ("Presentation report", "演示汇报"),
        ("Alarm screenshot", "告警截图"),
        ("Set display mode", "设置显示模式"),
        ("Carousel video", "轮播视频"),
        ("Video sort", "视频排序"),
        ("Event list", "事件列表"),
        ("Carousel event", "轮播事件"),
        ("Event sort", "事件排序"),
        ("Mode switch", "模式切换"),
        ("single", "单路"),
        ("ascending by object name", "按对象名称正序"),
        ("descending by object name", "按对象名称倒序"),
        ("ascending by creation time", "按创建时间正序"),
        ("descending by creation time", "按创建时间倒序"),
        ("ascending by time", "按时间正序"),
        ("descending by time", "按时间倒序"),
        ("spring", "春季"),
        ("summer", "夏季"),
        ("autumn", "秋季"),
        ("fall", "秋季"),
        ("winter", "冬季"),
        ("sunny intervals", "晴间多云"),
        ("sunny", "晴"),
        ("cloudy", "阴天"),
        ("light rain", "小雨"),
        ("moderate rain", "中雨"),
        ("heavy rain", "大雨"),
        ("light snow", "小雪"),
        ("moderate snow", "中雪"),
        ("heavy snow", "大雪"),
        ("fog", "雾"),
        ("haze", "霾"),
        ("sand", "扬沙"),
    ],
    key=lambda item: len(item[0]),
    reverse=True,
)


def _load_entity_alias_entries() -> list[dict[str, Any]]:
    if not ENTITY_ALIAS_FILE.exists():
        return []
    parsed = _safe_json_loads(ENTITY_ALIAS_FILE.read_text(encoding="utf-8"))
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [value for value in parsed.values() if isinstance(value, dict)]
    return []


def _build_entity_display_replacements(entries: list[dict[str, Any]]) -> list[tuple[str, str]]:
    replacements: dict[str, str] = {}
    for entry in entries:
        display_name = str(entry.get("display_name_en") or entry.get("system_name") or "").strip()
        if not display_name:
            continue
        candidates = [
            str(entry.get("system_name") or "").strip(),
            *_list_values(entry.get("aliases_zh")),
        ]
        for candidate in candidates:
            normalized_candidate = str(candidate).strip()
            if not normalized_candidate or not re.search(r"[\u4e00-\u9fff]", normalized_candidate):
                continue
            replacements[normalized_candidate] = display_name
    return sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)

DIRECT_INFO_PREFIXES: set[str] = {
    "A01", "A02", "A07", "A08", "A10", "A11", "A12", "A15", "A16", "A17", "A18",
    "A19", "A22", "A23", "A24", "A25", "A26", "A27", "A28", "A29", "A39",
    "B01", "B02", "B06", "B07", "B08", "B09", "B10", "B13", "B14", "C01", "C02",
    "E01", "E02", "E03", "E04", "E07",
    "E12", "E13", "E14", "E15", "E16",
    "E21", "E24", "E25", "E26", "E27",
    "E34",
}

# B11/B12 固定计划文本（显隐路径指令）
FIXED_PLAN_TEXT: dict[str, dict[str, str]] = {
    "B11": {
        "zh-CN": "已查询到小会议室的位置。并为您提供了去小会议室的路径",
        "en-US": "The location of the small meeting room has been found. A path to the small meeting room has been provided for you.",
    },
    "B12": {
        "zh-CN": "已查询到打印机的位置。并为您提供了去打印机的路径",
        "en-US": "The location of the printer has been found. A path to the printer has been provided for you.",
    },
}

DEMO_PREFIXES: set[str] = {"A30"}

FIXED_CHINESE_PREFIXES: set[str] = {
    "A01", "A07", "A08", "A10", "A11", "A12", "A16", "A17", "A22", "A25",
    "A27", "A28", "A29", "A39",
    "E02", "E03", "E04", "E12", "E13", "E15", "E21",
}


class SkillRuntimeError(Exception):
    pass


def _normalize_base_url(base_url: str | None) -> str:
    normalized = str(base_url or DEFAULT_TWINEASY_BASE_URL).strip().rstrip("/")
    for suffix in ("/api/editor/v1", "/api/editor/mcp", "/api/editor"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.rstrip("/")


def _get_server_url(base_url: str | None = None) -> str:
    if base_url:
        return f"{_normalize_base_url(base_url)}/api/editor"
    return DEFAULT_TWINEASY_SERVER_URL


def _get_mcp_base_url(base_url: str | None = None) -> str:
    if base_url:
        return f"{_normalize_base_url(base_url)}/api/editor/mcp"
    return DEFAULT_MCP_BASE_URL


def _safe_json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


ENTITY_ALIAS_ENTRIES: list[dict[str, Any]] = _load_entity_alias_entries()
ENTITY_DISPLAY_REPLACEMENTS: list[tuple[str, str]] = _build_entity_display_replacements(ENTITY_ALIAS_ENTRIES)

EN_DISPLAY_LABELS: dict[str, str] = {
    "A02": "Level",
    "B01": "Focus on",
    "B02": "Select object",
}

DEVICE_CONTROL_EN_ACTIONS: dict[str, str] = {
    "B07": "Turn on",
    "B08": "Turn off",
    "B09": "Turn on",
    "B10": "Turn off",
}

VIDEO_COMMAND_EN_ACTIONS: dict[str, str] = {
    "E02": "Set display mode to",
    "E03": "video carousel",
    "E04": "Sort videos",
    "E12": "event list",
    "E13": "event carousel",
    "E15": "Sort events",
    "E21": "Switch time mode to",
}


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
    structured_items = [item for item in normalized_items if not isinstance(item, str)]
    if len(structured_items) == 1:
        return structured_items[0]
    if structured_items:
        return structured_items
    if texts and len(texts) == len(normalized_items):
        return "\n".join(texts)
    return normalized_items


async def _post_mcp_json_rpc(
    client: httpx.AsyncClient,
    token: str,
    method: str,
    params: dict[str, Any] | None,
    mcp_base_url: str,
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
    response = await client.post(mcp_base_url, headers=headers, json=payload)

    if response.status_code >= 400:
        response_text = response.text.strip()
        raise SkillRuntimeError(
            f"MCP 请求失败(method={method}) status={response.status_code} url={response.request.url} body={response_text}"
        )

    next_session_id = response.headers.get("Mcp-Session-Id") or mcp_session_id
    parsed = _parse_mcp_response_payload(response, request_id) if expect_response else None
    return parsed, next_session_id


async def _ensure_mcp_initialized(client: httpx.AsyncClient, session: SessionState, token: str, mcp_base_url: str) -> None:
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
        mcp_base_url=mcp_base_url,
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
        mcp_base_url=mcp_base_url,
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
    mcp_base_url: str,
) -> Any:
    try:
        await _ensure_mcp_initialized(client, session, token, mcp_base_url)
        response_payload, next_session_id = await _post_mcp_json_rpc(
            client=client,
            token=token,
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
            mcp_base_url=mcp_base_url,
            mcp_session_id=session.mcp_session_id or None,
            expect_response=True,
        )
    except SkillRuntimeError as exc:
        if session.mcp_session_id and "status=404" in str(exc):
            session.mcp_session_id = ""
            session.mcp_initialized = False
            await _ensure_mcp_initialized(client, session, token, mcp_base_url)
            response_payload, next_session_id = await _post_mcp_json_rpc(
                client=client,
                token=token,
                method="tools/call",
                params={"name": tool_name, "arguments": arguments},
                mcp_base_url=mcp_base_url,
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


async def _fetch_scene_info(client: httpx.AsyncClient, session: SessionState, token: str, mcp_base_url: str) -> Any:
    return await _invoke_mcp_tool(client, session, "get_scene_info", {"token": token}, token, mcp_base_url)


def _normalize_command_token(command: str) -> str:
    return str(command or "").strip().upper().rstrip("：:")


def _get_command_prefix(command: str) -> str:
    return _normalize_command_token(command)[:3]


def _normalize_instruction_command(command: str) -> str:
    return _canonicalize_instruction_command(command)


def _detect_locale(text: str | None) -> str:
    value = str(text or "")
    if any(ord(ch) > 127 and '\u4e00' <= ch <= '\u9fff' for ch in value):
        return "zh-CN"
    if re.search(r"[A-Za-z]", value):
        return "en-US"
    return "zh-CN"


def _message(locale: str, key: str, **kwargs: Any) -> str:
    template = PLAN_MESSAGES.get(locale, PLAN_MESSAGES["zh-CN"]).get(key) or PLAN_MESSAGES["zh-CN"][key]
    return template.format(**kwargs)


def _translate_entity_display_names(text: str, locale: str) -> str:
    if locale != "en-US":
        return text
    translated = str(text or "")
    for source, target in ENTITY_DISPLAY_REPLACEMENTS:
        translated = translated.replace(source, target)
    return translated


def _translate_text(text: str, locale: str) -> str:
    if locale != "en-US":
        return text
    translated = _translate_entity_display_names(str(text or ""), locale)
    for source, target in EN_TEXT_REPLACEMENTS:
        translated = translated.replace(source, target)
    translated = translated.replace("：", ": ").replace("，", ", ").replace("、", ", ")
    for phrase in EN_TEXT_BOUNDARY_PHRASES:
        translated = re.sub(rf"(?<=[A-Za-z])(?={re.escape(phrase)})", " ", translated)
    translated = re.sub(r"\s{2,}", " ", translated)
    return translated.strip()


def _replace_case_insensitive(text: str, source: str, target: str) -> str:
    return re.sub(re.escape(source), target, text, flags=re.IGNORECASE)


def _canonicalize_fixed_chinese_command(command: str) -> str:
    normalized = str(command or "").strip()
    if not normalized:
        return ""

    normalized = normalized.replace("2x2", "2×2").replace("3x3", "3×3")
    normalized = normalized.replace("2X2", "2×2").replace("3X3", "3×3")
    for source, target in EN_TO_ZH_FIXED_REPLACEMENTS:
        normalized = _replace_case_insensitive(normalized, source, target)
    normalized = normalized.replace(":", "：")
    normalized = re.sub(r"\s*：\s*", "：", normalized)
    normalized = re.sub(r"\s*，\s*", "，", normalized)
    normalized = re.sub(r"\s*,\s*", "，", normalized)
    return normalized.strip()


def _canonicalize_instruction_command(command: str) -> str:
    stripped = str(command or "").strip()
    if not stripped:
        return ""

    command_prefix = _get_command_prefix(stripped)
    if command_prefix in NO_ARG_COMMAND_TEXT:
        return command_prefix
    if command_prefix in FIXED_CHINESE_PREFIXES:
        return _canonicalize_fixed_chinese_command(stripped)
    return stripped


def _extract_info(command: str) -> str:
    parts = re.split(r"[：:]", command, maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()
    return command.strip() if command else ""


def _extract_command_value(command: str) -> str:
    parts = [part.strip() for part in re.split(r"[：:]", command, maxsplit=2)]
    if len(parts) >= 3:
        return parts[2]
    if len(parts) >= 2:
        return parts[1]
    return str(command or "").strip()


def _strip_suffix_case_insensitive(text: str, suffixes: tuple[str, ...]) -> str:
    normalized = str(text or "").strip()
    for suffix in suffixes:
        pattern = rf"\s*{re.escape(suffix)}\s*$"
        updated = re.sub(pattern, "", normalized, flags=re.IGNORECASE).strip()
        if updated != normalized:
            return updated
    return normalized


def _extract_structured_segments(command: str) -> tuple[str, str, str]:
    body = _extract_info(command)
    colon_parts = [part.strip() for part in re.split(r"[：:]", body, maxsplit=1)]
    section = colon_parts[0] if colon_parts else ""
    detail = colon_parts[1] if len(colon_parts) > 1 else ""
    if not detail:
        return "", section, ""

    comma_parts = [part.strip() for part in re.split(r"[，,]", detail, maxsplit=1)]
    subject = comma_parts[0] if comma_parts else ""
    value = comma_parts[1] if len(comma_parts) > 1 else ""
    return section, subject, value


def _render_video_command_en_display(command: str) -> str | None:
    command_prefix = _get_command_prefix(command)
    if command_prefix not in VIDEO_COMMAND_EN_ACTIONS:
        return None

    _section, subject, value = _extract_structured_segments(command)
    translated_subject = _translate_text(subject, "en-US")
    translated_value = _translate_text(value, "en-US")

    if command_prefix == "E02":
        return f"Set display mode to {translated_value}" if translated_value else "Set display mode"

    if command_prefix == "E03":
        action = translated_value.capitalize() if translated_value else "Control"
        return f"{action} video carousel"

    if command_prefix == "E04":
        return f"Sort videos {translated_value}" if translated_value else "Sort videos"

    if command_prefix == "E12":
        normalized_value = translated_value.lower()
        if normalized_value == "select":
            return "Select event list"
        if normalized_value == "cancel":
            return "Clear event list selection"
        return f"Event list: {translated_value}" if translated_value else "Event list"

    if command_prefix == "E13":
        action = translated_value.capitalize() if translated_value else "Control"
        return f"{action} event carousel"

    if command_prefix == "E15":
        return f"Sort events {translated_value}" if translated_value else "Sort events"

    if command_prefix == "E21":
        return f"Switch time mode to {translated_value}" if translated_value else "Switch time mode"

    if translated_value:
        return f"{translated_subject}: {translated_value}" if translated_subject else translated_value
    return translated_subject or None


def _render_device_control_en_display(command: str) -> str | None:
    command_prefix = _get_command_prefix(command)
    action = DEVICE_CONTROL_EN_ACTIONS.get(command_prefix)
    if not action:
        return None

    value = _translate_text(_extract_command_value(command), "en-US")
    value = re.sub(r"\s{2,}", " ", value).strip(" :,.")
    if not value:
        return action

    if command_prefix in {"B07", "B08"}:
        location = _strip_suffix_case_insensitive(value, ("light switch", "lights"))
        if location and location != value:
            return f"{action} the light switch in {location}"
        return f"{action} {value}" if re.search(r"\blight switch\b|\blights\b", value, re.IGNORECASE) else f"{action} the lights in {value}"

    location = _strip_suffix_case_insensitive(value, ("air conditioner", "thermostat", "temperature controller", "hvac"))
    if location and location != value:
        return f"{action} the air conditioner in {location}"
    return f"{action} {value}" if re.search(r"\bair conditioner\b|\bthermostat\b|\bhvac\b", value, re.IGNORECASE) else f"{action} the air conditioner in {value}"


def _render_structured_en_display(command: str) -> str | None:
    device_control_display = _render_device_control_en_display(command)
    if device_control_display is not None:
        return device_control_display

    video_command_display = _render_video_command_en_display(command)
    if video_command_display is not None:
        return video_command_display

    command_prefix = _get_command_prefix(command)
    label = EN_DISPLAY_LABELS.get(command_prefix)
    if not label:
        return None
    value = _translate_text(_extract_command_value(command), "en-US")
    if value:
        return f"{label}: {value}"
    return label


def _get_display_text(command: str, locale: str) -> str:
    command_prefix = _get_command_prefix(command)
    if command_prefix in NO_ARG_COMMAND_TEXT:
        if locale == "en-US":
            return EN_NO_ARG_COMMAND_TEXT.get(command_prefix, NO_ARG_COMMAND_TEXT[command_prefix])
        return NO_ARG_COMMAND_TEXT[command_prefix]
    if command_prefix in FIXED_PLAN_TEXT:
        return FIXED_PLAN_TEXT[command_prefix].get(locale, FIXED_PLAN_TEXT[command_prefix]["zh-CN"])
    if locale == "en-US":
        structured_display = _render_structured_en_display(command)
        if structured_display is not None:
            return structured_display
    if not re.search(r"[：:]", command):
        return _message(locale, "failure_prefix") + _normalize_command_token(command)
    extracted = _extract_info(command)
    if command_prefix in DIRECT_INFO_PREFIXES:
        return _translate_text(extracted, locale)
    if command_prefix in DEMO_PREFIXES:
        return _message(locale, "presentation_prefix") + _translate_text(extracted, locale)
    return _message(locale, "failure_prefix") + _translate_text(command, locale)


def _process_single_command(command: str, locale: str) -> str:
    command_prefix = _get_command_prefix(command)

    if command.startswith("D"):
        parts = re.split(r"[：:]", command, maxsplit=1)
        if len(parts) > 1:
            return _message(locale, "query_result_prefix") + _translate_text(parts[1].strip(), locale)
        if len(command) >= 4:
            return _message(locale, "query_result_prefix") + _translate_text(command[3:], locale)
        return _message(locale, "failure_prefix") + ("字符串长度不足" if locale == "zh-CN" else "insufficient command length")

    if command_prefix == "E35":
        parts = re.split(r"[：:]", command, maxsplit=1)
        if len(parts) > 1:
            names_part = parts[1].strip()
            if names_part.startswith("名称："):
                names_part = names_part[3:].strip()
            names = [n.strip() for n in names_part.split("，") if n.strip()]
            translated_names = [_translate_text(name, locale) for name in names]
            cnt = len(names)
            separator = "、" if locale == "zh-CN" else ", "
            return _message(locale, "camera_names_prefix", names=separator.join(translated_names), count=cnt)
        return _message(locale, "query_result_prefix") + ("（无数据）" if locale == "zh-CN" else "(no data)")

    return _get_display_text(command, locale)


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


def _build_execution_plan(agent_text: str, locale: str) -> tuple[str, str]:
    raw_instruction_order = _extract_last_bracket_content(agent_text)
    raw_commands = raw_instruction_order.strip().split("$") if raw_instruction_order.strip() else []
    normalized_commands = [_normalize_instruction_command(cmd) for cmd in raw_commands if cmd.strip()]
    instruction_order = "$".join(cmd.strip() for cmd in normalized_commands if cmd.strip())

    has_failure = False
    failure_result = ""
    results: list[str] = []

    for index, command in enumerate(normalized_commands, 1):
        current = command.strip()
        if not current:
            continue
        content = _process_single_command(current, locale)
        if "执行失败" in content:
            has_failure = True
            failure_result = content
            break
        if locale == "en-US" and content.startswith("Execution failed"):
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
            plan_header = _message(locale, "plan_header")
            final_result = plan_header + "\n".join(results)
    else:
        final_result = _message(locale, "no_instruction")

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


def _build_json_data(instruction_order: str, query: str, plan_text: str) -> str:
    expanded = _expand_instruction_order(instruction_order)
    return f"{expanded}$&{query}$&{plan_text}"


async def _send_instruction(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    instruction_order: str,
    plan_text: str,
    server_url: str,
) -> Any:
    json_data = _build_json_data(instruction_order, query, plan_text)
    response = await client.post(
        f"{server_url}/v1/location/SendInstruction",
        headers={"Content-Type": "application/json", "Accept": "text/plain"},
        json={"token": token, "jsonData": json_data},
    )
    if response.status_code >= 400:
        raise SkillRuntimeError(f"孪易指令发送失败: {response.text}")
    return _safe_json_loads(response.text) or response.text


def _dispatch_instruction_send(
    token: str,
    json_data: str,
    server_url: str,
) -> None:
    worker_script = Path(__file__).resolve().parent / "send_instruction_worker.py"
    cmd = [
        sys.executable,
        str(worker_script),
        "--token",
        token,
        "--json-data",
        json_data,
        "--delay-seconds",
        str(BACKGROUND_SEND_DELAY_SECONDS),
        "--timeout-seconds",
        str(HTTP_TIMEOUT),
        "--server-url",
        server_url,
    ]

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )


async def get_scene_context(token: str, session_id: str = "default", base_url: str | None = None) -> dict[str, Any]:
    if not token:
        raise SkillRuntimeError("token 不能为空")

    mcp_base_url = _get_mcp_base_url(base_url)

    store = _load_session_store()
    session = _get_or_create_session(store, session_id)

    if session.token_judge and session.token_judge != token:
        session.reset_for_token(token)

    scene_info_error: str | None = None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        if not session.scene_info or session.token_judge != token:
            try:
                scene_info_raw = await _fetch_scene_info(client, session, token, mcp_base_url)
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


async def call_mcp_tool(
    token: str,
    tool_name: str,
    arguments: dict[str, Any],
    session_id: str = "default",
    base_url: str | None = None,
) -> Any:
    if not token:
        raise SkillRuntimeError("token 不能为空")
    if not tool_name:
        raise SkillRuntimeError("tool_name 不能为空")

    mcp_base_url = _get_mcp_base_url(base_url)

    store = _load_session_store()
    session = _get_or_create_session(store, session_id)

    if session.token_judge and session.token_judge != token:
        session.reset_for_token(token)
    elif not session.token_judge:
        session.token_judge = token

    if "token" not in arguments:
        arguments = {**arguments, "token": token}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        result = await _invoke_mcp_tool(client, session, tool_name, arguments, token, mcp_base_url)

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
    locale: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    if not token:
        raise SkillRuntimeError("token 不能为空")
    if not query:
        raise SkillRuntimeError("query 不能为空")
    if not agent_output:
        raise SkillRuntimeError("agent_output 不能为空")

    server_url = _get_server_url(base_url)

    resolved_locale = locale or _detect_locale(query)
    # 解析 agent_output，生成展示文本(plan_text) 与执行指令串(instruction_order)
    plan_text, instruction_order = _build_execution_plan(agent_text=agent_output, locale=resolved_locale)
    json_data = _build_json_data(instruction_order, query, plan_text)

    execution_result: Any = None
    if execute_instruction and instruction_order:
        _dispatch_instruction_send(token, json_data, server_url)
        execution_result = {
            "status": "queued",
            "delay_seconds": BACKGROUND_SEND_DELAY_SECONDS,
            "message": _message(resolved_locale, "queued_message"),
        }

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
        "locale": resolved_locale,
    }
    if execute_instruction:
        result["execution_result"] = execution_result
    if debug:
        result["debug_info"] = {
            "agent_raw_output": agent_output,
            "send_instruction_payload": {"token": token, "jsonData": json_data},
        }
    return result
