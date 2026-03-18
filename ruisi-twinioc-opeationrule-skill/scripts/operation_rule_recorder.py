#!/usr/bin/env python3
"""Operation rule recorder core — write and query rule records."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOG_FILE = Path(__file__).resolve().parent.parent / ".logs" / "operations.jsonl"
VALID_SOURCES = {"alarm", "temperature", "schedule"}
MAX_RECORDS_PER_SOURCE = 100


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_log_dir(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)


def write_record(
    token: str,
    source: str,
    query: str,
    log_file: Path = DEFAULT_LOG_FILE,
) -> dict[str, Any]:
    if not token:
        raise ValueError("token is required")
    if not query:
        raise ValueError("query is required")
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got: {source!r}")

    record: dict[str, Any] = {
        "time": utc_iso(datetime.now(timezone.utc)),
        "source": source,
        "token": token,
        "query": query,
    }

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
        token: filter by scene token.
        source: filter by trigger source (alarm/temperature/user).
        date: filter by date string YYYY-MM-DD (UTC).
        last: return only the last N records (applied after other filters).
        log_file: path to the .jsonl log file.
    """
    records = _load_all(log_file)

    if token:
        records = [r for r in records if r.get("token") == token]
    if source:
        records = [r for r in records if r.get("source") == source]
    if date:
        records = [r for r in records if r.get("time", "").startswith(date)]
    if last is not None and last > 0:
        records = records[-last:]

    return [{k: v for k, v in r.items() if k != "token"} for r in records]


def format_as_csv(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    fieldnames = ["time", "source", "query"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()
