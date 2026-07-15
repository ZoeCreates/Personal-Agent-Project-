from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_AUDIT_FILE = Path.home() / ".my-agent" / "tool_audit.jsonl"
MAX_ARG_CHARS = 4000
MAX_RESULT_CHARS = 1200


def audit_file_path() -> Path:
    return Path(os.getenv("MY_AGENT_TOOL_AUDIT_FILE") or DEFAULT_AUDIT_FILE).expanduser()


def log_tool_call(
    *,
    user_id: str,
    tool_name: str,
    args: dict[str, Any],
    allowed: bool,
    success: bool,
    result: str = "",
    duration_ms: int | None = None,
    error: str = "",
) -> None:
    if _env_bool("MY_AGENT_DISABLE_TOOL_AUDIT", False):
        return

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user_id": user_id,
        "tool_name": tool_name,
        "args": _truncate(args, MAX_ARG_CHARS),
        "allowed": allowed,
        "success": success,
        "duration_ms": duration_ms,
        "result_preview": _truncate(result, MAX_RESULT_CHARS),
        "error": error,
    }

    path = audit_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _truncate(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
