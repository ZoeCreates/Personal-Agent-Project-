import json
from datetime import datetime
from pathlib import Path
from core.paths import SESSIONS_DIR, ensure_data_dirs, migrate_legacy_data

migrate_legacy_data()


def init_db():
    ensure_data_dirs()


def _session_file(user_id: str) -> Path:
    safe_name = str(user_id).replace(":", "_")
    return SESSIONS_DIR / f"{safe_name}.jsonl"


def save_message(user_id: str, role: str, content: str):
    entry = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    with open(_session_file(user_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # AI 回复完成后检查是否需要触发 Dream 压缩
    if role == "assistant":
        from core.memory_compressor import maybe_compress

        maybe_compress(user_id)


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

    # 过滤孤立的 user 消息（紧接着的下一条不是 assistant 的）
    # summary 条目直接保留，不参与孤立消息过滤
    cleaned = []
    for i, m in enumerate(messages):
        if m["role"] == "summary":
            cleaned.append(m)
            continue
        if m["role"] == "user":
            next_role = None
            for j in range(i + 1, len(messages)):
                if messages[j].get("content"):
                    next_role = messages[j]["role"]
                    break
            if next_role != "assistant":
                continue
        cleaned.append(m)

    # 确保历史以 user 消息结尾（Anthropic 要求），summary 不算
    while cleaned and cleaned[-1]["role"] in ("assistant", "summary"):
        cleaned.pop()

    # 取最近 limit 条，加时间戳到 content 里
    # summary 条目不计入 limit（它是背景知识，不是对话轮次）
    summaries = [m for m in cleaned if m["role"] == "summary"]
    non_summaries = [m for m in cleaned if m["role"] != "summary"]
    recent = non_summaries[-limit:]

    result = []
    # 先把所有 summary 展开成 user/assistant 对，放在最前面
    for m in summaries:
        ts = m.get("timestamp", "")
        prefix = f"[{ts}] " if ts else ""
        result.append({"role": "user", "content": f"{prefix}[对话摘要] {m['content']}"})
        result.append(
            {"role": "assistant", "content": "好的，我已了解之前的对话内容。"}
        )

    # 再放最近的完整对话
    for m in recent:
        ts = m.get("timestamp", "")
        content = f"[{ts}] {m['content']}" if ts else m["content"]
        result.append({"role": m["role"], "content": content})

    return result


def clear_history(user_id: str):
    path = _session_file(user_id)
    if path.exists():
        path.unlink()
