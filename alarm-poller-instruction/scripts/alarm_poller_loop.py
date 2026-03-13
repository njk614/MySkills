#!/usr/bin/env python3
"""Run alarm_poller.py every interval with logs."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_POLLER_FILENAME = "alarm_poller.py"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description=f"Call {DEFAULT_POLLER_FILENAME} on a fixed interval with logs.")
    parser.add_argument(
        "--alarm-poller-path",
        default=None,
        help=f"Path to {DEFAULT_POLLER_FILENAME} (default: sibling script).",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Interval between runs (seconds).")
    parser.add_argument("--max-iterations", type=int, default=0, help="Stop after N runs (0 = infinite).")
    args, rest = parser.parse_known_args()
    if rest and rest[0] == "--":
        rest = rest[1:]
    return args, rest


def resolve_alarm_poller_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg).expanduser().resolve()
    return (Path(__file__).resolve().parent / DEFAULT_POLLER_FILENAME).resolve()


def run_alarm_poller(command: list[str]) -> int:
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as process:
        if process.stdout is None:
            return process.wait()

        try:
            for line in process.stdout:
                print(line, end="", flush=True)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise

        return process.wait()


def main() -> int:
    args, extra_args = parse_args()
    if args.interval <= 0:
        print("interval must be > 0", file=sys.stderr)
        return 2
    if args.max_iterations < 0:
        print("max-iterations must be >= 0", file=sys.stderr)
        return 2

    alarm_poller_path = resolve_alarm_poller_path(args.alarm_poller_path)
    if not alarm_poller_path.exists():
        print(f"{DEFAULT_POLLER_FILENAME} not found: {alarm_poller_path}", file=sys.stderr)
        return 2

    iteration = 0
    print(f"[{now_utc()}] loop start interval={args.interval}s max_iterations={args.max_iterations}")
    print(f"[{now_utc()}] alarm_poller_path={alarm_poller_path}")
    if extra_args:
        print(f"[{now_utc()}] alarm_poller_args={' '.join(extra_args)}")

    while True:
        iteration += 1
        started = time.monotonic()

        exit_code = run_alarm_poller([sys.executable, "-u", str(alarm_poller_path), *extra_args])

        print(
            # f"[{now_utc()}] run={iteration} exit_code={exit_code}",
            flush=True,
        )

        if args.max_iterations and iteration >= args.max_iterations:
            print(f"[{now_utc()}] loop stop (max_iterations reached)", flush=True)
            return exit_code

        elapsed = time.monotonic() - started
        sleep_seconds = max(0.0, args.interval - elapsed)
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
