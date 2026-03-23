#!/usr/bin/env python3
"""Operation rule recorder core — write and query rule records."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOG_FILE = Path(__file__).resolve().parent.parent / ".logs" / "operations.jsonl"
DEFAULT_PENDING_FILE = Path(__file__).resolve().parent.parent / ".runtime" / "pending_confirmations.json"
VALID_SOURCES = {"alarm", "temperature", "schedule"}
MAX_RECORDS_PER_SOURCE = 100

_TEMPERATURE_RULE_PATTERN = re.compile(
    r"(?:当|如果)?\s*(?P<device>.*?)\s*温度\s*"
    r"(?P<operator>大于等于|小于等于|不低于|不高于|高于|低于|大于|小于|超过|少于|>=|<=|>|<|等于|=)\s*"
    r"(?P<threshold>-?\d+(?:\.\d+)?)\s*(?:℃|度)?\s*"
    r"(?:时|后|的话|的时候|则|就)?[，,、\s]*(?P<action>.+)",
)

_ALARM_RULE_PATTERN = re.compile(
    r"(?:当|如果)?\s*(?P<device>.*?)\s*(?:产生|发生)?\s*告警\s*"
    r"(?:时|后|的话|的时候|则|就)?[，,、\s]*(?P<action>.+)",
)

_OPERATOR_ALIASES: dict[str, tuple[str, str]] = {
    ">": ("gt", "大于"),
    "大于": ("gt", "大于"),
    "高于": ("gt", "大于"),
    "超过": ("gt", "大于"),
    "<": ("lt", "小于"),
    "小于": ("lt", "小于"),
    "低于": ("lt", "小于"),
    "少于": ("lt", "小于"),
    ">=": ("gte", "大于等于"),
    "大于等于": ("gte", "大于等于"),
    "不低于": ("gte", "大于等于"),
    "<=": ("lte", "小于等于"),
    "小于等于": ("lte", "小于等于"),
    "不高于": ("lte", "小于等于"),
    "=": ("eq", "等于"),
    "等于": ("eq", "等于"),
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _normalize_threshold_text(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _normalize_action_text(action: str) -> str:
    cleaned = re.sub(r"^(请|帮我|帮忙|麻烦|需要|要|将)", "", action.strip())
    cleaned = cleaned.strip("，,。；; ")
    return cleaned or action.strip()


def _build_execute_query(device_name: str, action_text: str) -> str:
    if not device_name or device_name in action_text:
        return action_text

    action = action_text.strip()
    match = re.match(r"^(打开|开启|关闭|关掉)(.+)$", action)
    if match:
        verb = match.group(1)
        target = match.group(2).strip()
        return f"{verb}{device_name}{target}"
    return f"{device_name}{action}"


def parse_temperature_rule(query: str) -> dict[str, Any] | None:
    match = _TEMPERATURE_RULE_PATTERN.search(str(query or "").strip())
    if not match:
        return None

    device_name = match.group("device").strip().strip("，,。；; ")
    operator_raw = match.group("operator")
    operator_info = _OPERATOR_ALIASES.get(operator_raw)
    if not device_name or not operator_info:
        return None

    threshold = float(match.group("threshold"))
    action_text = _normalize_action_text(match.group("action"))
    operator, operator_text = operator_info

    return {
        "kind": "temperature_threshold",
        "device_name": device_name,
        "operator": operator,
        "operator_text": operator_text,
        "threshold": threshold,
        "threshold_text": _normalize_threshold_text(threshold),
        "action_text": action_text,
        "execute_query": _build_execute_query(device_name, action_text),
    }


def parse_alarm_rule(query: str) -> dict[str, Any] | None:
    match = _ALARM_RULE_PATTERN.search(str(query or "").strip())
    if not match:
        return None

    device_name = match.group("device").strip().strip("，,。；; ")
    if not device_name:
        return None

    action_text = _normalize_action_text(match.group("action"))
    if not action_text:
        return None

    return {
        "kind": "alarm_trigger",
        "device_name": device_name,
        "action_text": action_text,
        "execute_query": _build_execute_query(device_name, action_text),
    }


def _compare_temperature(current: float, operator: str, threshold: float) -> bool:
    if operator == "gt":
        return current > threshold
    if operator == "gte":
        return current >= threshold
    if operator == "lt":
        return current < threshold
    if operator == "lte":
        return current <= threshold
    if operator == "eq":
        return abs(current - threshold) < 1e-9
    return False


def _build_confirmation_text(device_name: str, temperature: float, parsed_rule: dict[str, Any]) -> str:
    temperature_text = _normalize_threshold_text(temperature)
    threshold_text = parsed_rule.get("threshold_text") or _normalize_threshold_text(float(parsed_rule["threshold"]))
    operator_text = str(parsed_rule.get("operator_text") or "")
    action_text = str(parsed_rule.get("action_text") or "").strip()
    return (
        f"当前{device_name}{temperature_text}℃，"
        f"{operator_text}规则设定的{operator_text}{threshold_text}℃，"
        f"{action_text}，请确认是否执行？"
    )


def _record_with_parsed_rule(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source")
    if source not in {"temperature", "alarm"}:
        return record
    if isinstance(record.get("parsed_rule"), dict):
        return record

    query_text = str(record.get("query") or "")
    parsed_rule = parse_temperature_rule(query_text) if source == "temperature" else parse_alarm_rule(query_text)
    if not parsed_rule:
        return record

    enriched = dict(record)
    enriched["parsed_rule"] = parsed_rule
    return enriched


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_log_dir(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)


def _ensure_parent_dir(file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)


def _load_pending_map(pending_file: Path = DEFAULT_PENDING_FILE) -> dict[str, dict[str, Any]]:
    if not pending_file.exists():
        return {}
    try:
        parsed = json.loads(pending_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _save_pending_map(pending_map: dict[str, dict[str, Any]], pending_file: Path = DEFAULT_PENDING_FILE) -> None:
    _ensure_parent_dir(pending_file)
    pending_file.write_text(json.dumps(pending_map, ensure_ascii=False, indent=2), encoding="utf-8")


def write_record(
    token: str | None,
    source: str,
    query: str,
    log_file: Path = DEFAULT_LOG_FILE,
) -> dict[str, Any]:
    # token is accepted for compatibility but is not stored in records.
    if not query:
        raise ValueError("query is required")
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got: {source!r}")

    record: dict[str, Any] = {
        "time": utc_iso(datetime.now(timezone.utc)),
        "source": source,
        "query": query,
    }
    if source in {"temperature", "alarm"}:
        parsed_rule = parse_temperature_rule(query) if source == "temperature" else parse_alarm_rule(query)
        if parsed_rule:
            record["parsed_rule"] = parsed_rule

    _ensure_log_dir(log_file)

    # Load all existing records, append new one, then enforce per-source cap.
    all_records = _load_all(log_file)
    all_records.append(record)

    # Keep only the last MAX_RECORDS_PER_SOURCE records per source.
    by_source: dict[str, list[dict[str, Any]]] = {}
    for r in all_records:
        s = r.get("source", "")
        by_source.setdefault(s, []).append(r)
    for s in by_source:
        if len(by_source[s]) > MAX_RECORDS_PER_SOURCE:
            by_source[s] = by_source[s][-MAX_RECORDS_PER_SOURCE:]

    # Merge back preserving original time order.
    merged = sorted(
        (r for records in by_source.values() for r in records),
        key=lambda r: r.get("time", ""),
    )

    with log_file.open("w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return record


def _load_all(log_file: Path) -> list[dict[str, Any]]:
    if not log_file.exists():
        return []
    records: list[dict[str, Any]] = []
    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def query_records(
    token: str | None = None,
    source: str | None = None,
    date: str | None = None,
    last: int | None = None,
    log_file: Path = DEFAULT_LOG_FILE,
) -> list[dict[str, Any]]:
    """Query rule records with optional filters.

    Args:
        token: accepted for compatibility but ignored (records no longer store token).
        source: filter by trigger source (alarm/temperature/user).
        date: filter by date string YYYY-MM-DD (UTC).
        last: return only the last N records (applied after other filters).
        log_file: path to the .jsonl log file.
    """
    records = _load_all(log_file)
    if source:
        records = [r for r in records if r.get("source") == source]
    if date:
        records = [r for r in records if r.get("time", "").startswith(date)]
    if last is not None and last > 0:
        records = records[-last:]
    return [ _record_with_parsed_rule(r) for r in records ]


def match_temperature_rules(
    temperature: float,
    device_name: str,
    token: str | None = None,
    log_file: Path = DEFAULT_LOG_FILE,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    normalized_device_name = _normalize_text(device_name)

    for record in _load_all(log_file):
        # token is ignored for matching — any recorded temperature rule may apply
        if record.get("source") != "temperature":
            continue

        enriched_record = _record_with_parsed_rule(record)
        parsed_rule = enriched_record.get("parsed_rule")
        if not isinstance(parsed_rule, dict):
            continue

        rule_device_name = str(parsed_rule.get("device_name") or "")
        normalized_rule_device_name = _normalize_text(rule_device_name)
        if normalized_rule_device_name and normalized_rule_device_name not in normalized_device_name and normalized_device_name not in normalized_rule_device_name:
            continue

        threshold = float(parsed_rule["threshold"])
        operator = str(parsed_rule.get("operator") or "")
        if not _compare_temperature(temperature, operator, threshold):
            continue

        matched_record = {k: v for k, v in enriched_record.items() if k != "token"}
        matched_record["current_temperature"] = temperature
        matched_record["confirmation_text"] = _build_confirmation_text(device_name, temperature, parsed_rule)

        matches.append(matched_record)

    # Return only the latest matching rule (by time) if any
    if not matches:
        return []
    latest = max(matches, key=lambda m: m.get("time", ""))
    return [latest]


def match_alarm_rules(
    device_name: str,
    token: str | None = None,
    log_file: Path = DEFAULT_LOG_FILE,
) -> list[dict[str, Any]]:
    """Find latest alarm record that mentions the device_name.

    Matching is a simple normalized substring check against the record `query`.
    Token is accepted for compatibility but ignored.
    Returns at most one (latest) matching record in a list.
    """
    matches: list[dict[str, Any]] = []
    normalized_device_name = _normalize_text(device_name)

    for record in _load_all(log_file):
        if record.get("source") != "alarm":
            continue

        enriched_record = _record_with_parsed_rule(record)
        parsed_rule = enriched_record.get("parsed_rule")
        rule_device_name = ""
        if isinstance(parsed_rule, dict):
            rule_device_name = str(parsed_rule.get("device_name") or "")
        normalized_rule_device_name = _normalize_text(rule_device_name)

        query_text = str(record.get("query") or "")
        normalized_query = _normalize_text(query_text)

        if not normalized_device_name:
            continue

        # Prefer structured device matching when available, then fall back to raw query substring matching.
        structured_match = False
        if normalized_rule_device_name:
            structured_match = (
                normalized_device_name in normalized_rule_device_name
                or normalized_rule_device_name in normalized_device_name
            )

        raw_query_match = normalized_device_name in normalized_query or normalized_query in normalized_device_name

        if structured_match or raw_query_match:
            matched_record = {k: v for k, v in enriched_record.items() if k != "token"}
            matches.append(matched_record)

    if not matches:
        return []
    latest = max(matches, key=lambda m: m.get("time", ""))
    return [latest]


def handle_incoming_alarm(
    device_name: str,
    alarm_source: str = "camera",
    log_file: Path = DEFAULT_LOG_FILE,
) -> dict[str, Any] | None:
    """Handle an incoming alarm event (e.g., from camera) and return the latest related rule.

    - `device_name`: the device/location reported by the alarm source.
    - `alarm_source`: source of alarm (currently informational; matching ignores it because
      records are matched by device/query content). Defaults to 'camera'.

    Returns the latest matching record dict (with any parsed_rule) or None if no match.
    """
    matches = match_alarm_rules(device_name=device_name, token=None, log_file=log_file)
    if not matches:
        return None

    # matches already returns latest as single-item list
    latest = matches[0]

    # Try to extract an actionable instruction from the matched query
    enriched_latest = _record_with_parsed_rule(latest)
    parsed_rule = enriched_latest.get("parsed_rule")
    if isinstance(parsed_rule, dict):
        action_text = str(parsed_rule.get("action_text") or "").strip()
        execute_query = str(parsed_rule.get("execute_query") or "").strip()
    else:
        action_text, execute_query = None, None

    if not action_text or not execute_query:
        action_text, execute_query = _parse_alarm_action(latest.get("query", ""), device_name)
    if action_text:
        latest = dict(enriched_latest)
        latest["action_text"] = action_text
        latest["execute_query"] = execute_query
        latest["confirmation_text"] = f"检测到{device_name}告警，{action_text}，请确认是否执行？"
        return latest

    # Fallback: return the matched record with a generic confirmation asking user to confirm the recorded query
    latest = dict(enriched_latest)
    latest["confirmation_text"] = f"检测到{device_name}告警，匹配到记录：{latest.get('query')}，请确认是否执行？"
    latest["execute_query"] = latest.get("query")
    return latest


def _parse_alarm_action(query: str, device_name: str) -> tuple[str | None, str | None]:
    """Try to parse a short action instruction from an alarm record's query.

    Returns (action_text, execute_query) or (None, None) if not found.
    The parser looks for common Chinese action verbs and extracts the verb and its object.
    """
    if not query:
        return None, None

    verbs = ["打开", "开启", "关闭", "关掉", "复位", "执行", "停止", "重启", "禁用", "启用"]
    for v in verbs:
        m = re.search(fr"({v}.+)", query)
        if m:
            action = m.group(1).strip().strip("，,。；; ")
            execute = _build_execute_query(device_name, action)
            return action, execute

    # If no verb-based match, try splitting by punctuation and take the trailing phrase
    parts = re.split(r"[，,;；：:]", query)
    if len(parts) > 1:
        action = parts[-1].strip()
        if action:
            execute = _build_execute_query(device_name, action)
            return action, execute

    return None, None


def save_pending_confirmation(
    token: str,
    source: str,
    confirmation_text: str,
    execute_query: str,
    matched_rule: dict[str, Any] | None = None,
    pending_file: Path = DEFAULT_PENDING_FILE,
) -> dict[str, Any]:
    if not token:
        raise ValueError("token is required")
    if not execute_query:
        raise ValueError("execute_query is required")

    pending_map = _load_pending_map(pending_file)
    pending_record: dict[str, Any] = {
        "time": utc_iso(datetime.now(timezone.utc)),
        "source": source,
        "confirmation_text": confirmation_text,
        "execute_query": execute_query,
    }
    if matched_rule is not None:
        pending_record["matched_rule"] = matched_rule

    pending_map[token] = pending_record
    _save_pending_map(pending_map, pending_file)
    return pending_record


def get_pending_confirmation(
    token: str,
    pending_file: Path = DEFAULT_PENDING_FILE,
) -> dict[str, Any] | None:
    if not token:
        raise ValueError("token is required")
    return _load_pending_map(pending_file).get(token)


def clear_pending_confirmation(
    token: str,
    pending_file: Path = DEFAULT_PENDING_FILE,
) -> bool:
    if not token:
        raise ValueError("token is required")

    pending_map = _load_pending_map(pending_file)
    existed = token in pending_map
    if existed:
        pending_map.pop(token, None)
        _save_pending_map(pending_map, pending_file)
    return existed


def format_as_csv(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    fieldnames = ["time", "source", "query"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()
