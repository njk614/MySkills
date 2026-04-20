#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib import error, parse, request

DEFAULT_BASE_URL = os.getenv("TWINIOC_ENVMETRIC_BASE_URL", "http://172.16.1.29:18081").rstrip("/")
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_METRIC_LEVEL = "L3"
DEFAULT_FLOOR_NO = 20


def _build_url(base_url: str, path: str, query_params: dict[str, Any] | None = None) -> str:
    clean_base_url = str(base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    if not query_params:
        return f"{clean_base_url}{clean_path}"

    filtered_params = {
        key: value
        for key, value in query_params.items()
        if value is not None and str(value).strip() != ""
    }
    if not filtered_params:
        return f"{clean_base_url}{clean_path}"
    return f"{clean_base_url}{clean_path}?{parse.urlencode(filtered_params)}"


def _http_get_json(url: str, timeout: float) -> Any:
    req = request.Request(url, method="GET", headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset("utf-8")
        payload = response.read().decode(charset)
        return json.loads(payload) if payload else {}


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _handle_success(command: str, url: str, data: Any) -> int:
    _print_json(
        {
            "success": True,
            "command": command,
            "url": url,
            "data": data,
        }
    )
    return 0


def _handle_failure(command: str, url: str, exc: Exception) -> int:
    status_code: int | None = None
    response_text = ""
    if isinstance(exc, error.HTTPError):
        status_code = exc.code
        try:
            response_text = exc.read().decode(exc.headers.get_content_charset("utf-8"))
        except Exception:
            response_text = ""
    elif isinstance(exc, error.URLError):
        response_text = str(exc.reason)
    else:
        response_text = str(exc)

    _print_json(
        {
            "success": False,
            "command": command,
            "url": url,
            "status_code": status_code,
            "error": response_text or str(exc),
        }
    )
    return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query ruisi-twinioc environment metrics REST API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="环境指标 REST API 基础地址")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP 请求超时时间，单位秒")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("metrics-meta", help="查询系统支持的环境指标列表")
    subparsers.add_parser("areas-meta", help="查询系统支持的区域列表")

    sensors_parser = subparsers.add_parser("sensors", help="查询全部温度传感器当前结果")
    sensors_parser.add_argument("--install-location", help="按安装位置过滤")

    sensor_parser = subparsers.add_parser("sensor", help="查询单个温度传感器当前结果")
    sensor_parser.add_argument("--sensor-id", required=True, help="温度传感器 ID")

    latest_parser = subparsers.add_parser("area-latest", help="查询区域全部最新环境指标")
    latest_parser.add_argument("--area-name", required=True, help="区域名称，例如 主场")
    latest_parser.add_argument("--metric-level", default=DEFAULT_METRIC_LEVEL, help="指标层级，默认 L3")
    latest_parser.add_argument("--floor-no", type=int, default=DEFAULT_FLOOR_NO, help="楼层编号，默认 20")

    metric_latest_parser = subparsers.add_parser("area-metric-latest", help="查询区域单个指标最新值")
    metric_latest_parser.add_argument("--area-name", required=True, help="区域名称，例如 主场")
    metric_latest_parser.add_argument("--metric-code", required=True, help="指标代码，例如 temperature_compliance_rate")
    metric_latest_parser.add_argument("--metric-level", default=DEFAULT_METRIC_LEVEL, help="指标层级，默认 L3")
    metric_latest_parser.add_argument("--floor-no", type=int, default=DEFAULT_FLOOR_NO, help="楼层编号，默认 20")

    timeline_parser = subparsers.add_parser("area-metric-timeline", help="查询区域单个指标趋势")
    timeline_parser.add_argument("--area-name", required=True, help="区域名称，例如 主场")
    timeline_parser.add_argument("--metric-code", required=True, help="指标代码，例如 temperature_compliance_rate")
    timeline_parser.add_argument("--granularity", required=True, choices=("hourly", "daily", "weekly"), help="趋势粒度")
    timeline_parser.add_argument("--limit", type=int, default=24, help="返回数据点数量")
    timeline_parser.add_argument("--metric-level", default=DEFAULT_METRIC_LEVEL, help="指标层级，默认 L3")
    timeline_parser.add_argument("--floor-no", type=int, default=DEFAULT_FLOOR_NO, help="楼层编号，默认 20")

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    command = str(args.command)

    if command == "metrics-meta":
        url = _build_url(args.base_url, "/api/v1/env/meta/metrics")
    elif command == "areas-meta":
        url = _build_url(args.base_url, "/api/v1/env/meta/areas")
    elif command == "sensors":
        url = _build_url(
            args.base_url,
            "/api/v1/env/temperature/sensors",
            {"install_location": args.install_location},
        )
    elif command == "sensor":
        url = _build_url(
            args.base_url,
            f"/api/v1/env/temperature/sensors/{parse.quote(args.sensor_id, safe='')}",
        )
    elif command == "area-latest":
        url = _build_url(
            args.base_url,
            f"/api/v1/env/areas/{parse.quote(args.area_name, safe='')}/metrics/latest",
            {"metric_level": args.metric_level, "floor_no": args.floor_no},
        )
    elif command == "area-metric-latest":
        url = _build_url(
            args.base_url,
            f"/api/v1/env/areas/{parse.quote(args.area_name, safe='')}/metrics/{parse.quote(args.metric_code, safe='')}/latest",
            {"metric_level": args.metric_level, "floor_no": args.floor_no},
        )
    elif command == "area-metric-timeline":
        url = _build_url(
            args.base_url,
            f"/api/v1/env/areas/{parse.quote(args.area_name, safe='')}/metrics/{parse.quote(args.metric_code, safe='')}/timeline",
            {
                "granularity": args.granularity,
                "limit": args.limit,
                "metric_level": args.metric_level,
                "floor_no": args.floor_no,
            },
        )
    else:
        _print_json({"success": False, "error": f"Unsupported command: {command}"})
        return 1

    try:
        data = _http_get_json(url, timeout=args.timeout)
        return _handle_success(command, url, data)
    except Exception as exc:
        return _handle_failure(command, url, exc)


if __name__ == "__main__":
    raise SystemExit(main())