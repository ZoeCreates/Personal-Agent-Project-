"""
Dream 机制 — 记忆压缩
当对话历史超过阈值时，把旧的对话压缩成一段摘要，保留最近的完整对话。
"""

import json
from datetime import datetime
from pathlib import Path

COMPRESS_THRESHOLD = 30  # 超过这么多条就触发压缩
KEEP_RECENT = 10  # 压缩时保留最近几条不动

SESSIONS_DIR = Path.home() / ".my-agent" / "sessions"


def _session_file(user_id: str) -> Path:
    safe_name = str(user_id).replace(":", "_")
    return SESSIONS_DIR / f"{safe_name}.jsonl"


def maybe_compress(user_id: str) -> bool:
    """
    检查是否需要压缩，需要则执行。
    返回 True 表示执行了压缩，False 表示无需压缩。
    """
    path = _session_file(user_id)
    if not path.exists():
        return False

    lines = [
        l for l in path.read_text(encoding="utf-8").strip().splitlines() if l.strip()
    ]
    if len(lines) < COMPRESS_THRESHOLD:
        return False

    compress(user_id, lines)
    return True


def compress(user_id: str, lines: list = None):
    """
    执行压缩：
    1. 读取全部历史
    2. 前 N 条发给 LLM 生成摘要
    3. 重写文件：[摘要条目] + [最近 KEEP_RECENT 条]
    """
    path = _session_file(user_id)

    if lines is None:
        lines = [
            l
            for l in path.read_text(encoding="utf-8").strip().splitlines()
            if l.strip()
        ]

    messages = []
    for line in lines:
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # 跳过已有的 summary 条目，只对原始对话计数
    raw = [m for m in messages if m.get("role") != "summary"]
    to_compress = raw[:-KEEP_RECENT]  # 要压缩的旧对话
    to_keep_raw = raw[-KEEP_RECENT:]  # 保留的近期对话

    if not to_compress:
        return

    print(
        f"  [Dream] 用户 {user_id}：压缩 {len(to_compress)} 条 → 摘要，保留最近 {len(to_keep_raw)} 条"
    )

    # 把已有的旧 summary 也纳入压缩范围，合并成一条，避免 summary 累积
    old_summaries = [m for m in messages if m.get("role") == "summary"]
    summary_text = _summarize(old_summaries + to_compress)

    # 重写文件：[唯一一条合并 summary] + [最近对话]
    new_summary = {
        "role": "summary",
        "content": summary_text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    new_lines = [json.dumps(new_summary, ensure_ascii=False)]

    for m in to_keep_raw:
        new_lines.append(json.dumps(m, ensure_ascii=False))

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"  [Dream] 完成，文件从 {len(lines)} 行压缩至 {len(new_lines)} 行")

    # 同步更新跨 session 的长期记忆
    _update_memory_md(old_summaries + to_compress)


MEMORY_FILE = Path.home() / ".my-agent" / "MEMORY.md"


def _update_memory_md(messages: list) -> None:
    """
    根据对话内容重写 MEMORY.md（长期记忆，跨 session 持久）。
    LLM 读取现有内容 + 新对话，输出更新后的完整 Markdown。
    """
    from core.llm import LLMClient

    existing = MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else ""

    dialog_text = ""
    for m in messages:
        if m["role"] == "summary":
            role_label = "[历史摘要]"
        elif m["role"] == "user":
            role_label = "用户"
        else:
            role_label = "AI"
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        ts = m.get("timestamp", "")
        dialog_text += f"[{ts}] {role_label}：{content}\n"

    prompt = f"""请根据以下对话内容，更新用户的长期记忆文件。

要求：
- 保留并合并现有记忆中仍然有效的内容
- 从新对话中提取：用户偏好、重要事实、习惯、项目信息等
- 删除已过时或被新信息覆盖的条目
- 用 Markdown 格式输出，分 ## 标题分类
- 内容简洁，每条一行，不超过 200 字总计
- 只输出 Markdown 内容本身，不要任何解释

现有记忆：
{existing if existing else '（空）'}

新对话：
{dialog_text}

更新后的记忆："""

    llm = LLMClient()
    response = llm.chat(
        [
            {"role": "system", "content": "你是一个专门维护用户长期记忆的助手。"},
            {"role": "user", "content": prompt},
        ]
    )
    new_content = response.content.strip()
    if new_content:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(new_content, encoding="utf-8")
        print(f"  [Dream] MEMORY.md 已更新")


def _summarize(messages: list) -> str:
    """
    调用 LLM，把一段对话历史压缩成文字摘要。
    使用独立的一次性调用，不影响用户对话流。
    """
    from core.llm import LLMClient

    # 把消息整理成可读文本
    dialog_text = ""
    for m in messages:
        if m["role"] == "summary":
            role_label = "[历史摘要]"
        elif m["role"] == "user":
            role_label = "用户"
        else:
            role_label = "AI"
        ts = m.get("timestamp", "")
        content = m.get("content", "")
        if isinstance(content, list):
            # tool_use 等复杂结构，取文字部分
            content = " ".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        prefix = f"[{ts}] " if ts else ""
        dialog_text += f"{prefix}{role_label}：{content}\n"

    prompt = f"""请将以下对话历史压缩成一段简洁的摘要。

要求：
- 保留：用户的重要偏好、关键事实、重要决策、设置的提醒
- 忽略：简单的问候、重复的内容、不重要的闲聊
- 用第三人称描述（例如"用户询问了..."）
- 尽量简洁，100字以内

对话历史：
{dialog_text}

摘要："""

    llm = LLMClient()
    response = llm.chat(
        [
            {
                "role": "system",
                "content": "你是一个专门负责压缩对话历史的助手，请生成简洁准确的摘要。",
            },
            {"role": "user", "content": prompt},
        ]
    )
    return response.content.strip()
