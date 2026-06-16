import json
from pathlib import Path
from datetime import datetime

SESSIONS_DIR = Path.home() / ".my-agent" / "sessions"

def init_db():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

def _session_file(user_id: str) -> Path:
    safe_name = str(user_id).replace(":", "_")
    return SESSIONS_DIR / f"{safe_name}.jsonl"

def save_message(user_id: str, role: str, content: str):
    entry = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    with open(_session_file(user_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def load_history(user_id: str, limit: int = 20) -> list:
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

    # 过滤空 content
    messages = [m for m in messages if m.get("content")]

    # 过滤孤立的 user 消息（后面没有 assistant 回复的）
    cleaned = []
    for i, m in enumerate(messages):
        if m["role"] == "user":
            # 检查后面是否有 assistant 回复
            has_reply = any(
                messages[j]["role"] == "assistant"
                for j in range(i + 1, len(messages))
                if messages[j]["role"] in ("user", "assistant")
            )
            if not has_reply:
                continue  # 孤立消息，跳过
        cleaned.append(m)

    # 确保历史以 user 消息结尾（Anthropic 要求）
    while cleaned and cleaned[-1]["role"] == "assistant":
        cleaned.pop()

    # 取最近 limit 条，加时间戳到 content 里
    recent = cleaned[-limit:]
    result = []
    for m in recent:
        ts = m.get("timestamp", "")
        content = f"[{ts}] {m['content']}" if ts else m["content"]
        result.append({"role": m["role"], "content": content})

    return result

def clear_history(user_id: str):
    path = _session_file(user_id)
    if path.exists():
        path.unlink()
