from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

_COMMAND_RUNTIME_PATH = Path(__file__).resolve().parent.parent.parent / "ruisi-twinioc-command-skill" / "scripts" / "skill_runtime.py"

_spec = importlib.util.spec_from_file_location("ruisi_twinioc_command_skill_runtime", _COMMAND_RUNTIME_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"无法加载 command skill runtime: {_COMMAND_RUNTIME_PATH}")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)  # type: ignore[union-attr]

SkillRuntimeError = getattr(_module, "SkillRuntimeError")
call_mcp_tool = getattr(_module, "call_mcp_tool")

__all__ = ["SkillRuntimeError", "call_mcp_tool"]
