from __future__ import annotations

from typing import Any


FILE_WRITE_KEYWORDS = (
    "write_file",
    "overwrite",
    "write",
    "save",
    "create file",
    "update file",
    "edit file",
    "写入",
    "覆盖",
    "保存",
    "创建文件",
    "修改文件",
)

FILE_READ_KEYWORDS = (
    "read_file",
    "read",
    "open file",
    "show file",
    "读取",
    "打开文件",
    "看看文件",
)

FILE_LIST_KEYWORDS = (
    "list_files",
    "list files",
    "show files",
    "ls ",
    "列出",
    "文件列表",
)


def preferred_tool_for_latest_user_message(
    messages: list[dict[str, Any]],
    available_tool_names: set[str],
) -> str | None:
    latest = _latest_user_text(messages).lower()
    if not latest:
        return None

    if "write_file" in available_tool_names and _has_any(latest, FILE_WRITE_KEYWORDS):
        return "write_file"
    if "list_files" in available_tool_names and _has_any(latest, FILE_LIST_KEYWORDS):
        return "list_files"
    if "read_file" in available_tool_names and _has_any(latest, FILE_READ_KEYWORDS):
        return "read_file"
    return None


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            return content
    return ""


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)
