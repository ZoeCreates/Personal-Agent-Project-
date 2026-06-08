import json
import os
from pathlib import Path

SESSIONS_DIR = Path.home() / ".my-agent" / "sessions"

def init_db():
    """创建 sessions 目录"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

def _session_file(user_id: str) -> Path:
    safe_name = str(user_id).replace(":", "_")
    return SESSIONS_DIR / f"{safe_name}.jsonl"

def save_message(user_id: str, role: str, content: str):
    """追加一条消息到 JSONL 文件"""
    with open(_session_file(user_id), "a", encoding="utf-8") as f:
        f.write(json.dumps({"role": role, "content": content}, ensure_ascii=False) + "\n")

def load_history(user_id: str, limit: int = 20) -> list:
    """读取最近 N 条消息"""
    path = _session_file(user_id)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    messages = []
    for line in lines:
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages[-limit:]

def clear_history(user_id: str):
    """清空某用户的历史"""
    path = _session_file(user_id)
    if path.exists():
        path.unlink()
