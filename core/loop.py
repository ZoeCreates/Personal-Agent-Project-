from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from core.context import AgentContext
from core.memory import load_history, save_message
from core.runner import AgentRunner
from core.tools import TOOLS


class AgentLoop:
    """Channel/session-facing loop: build context, call runner, and persist replies."""

    def __init__(
        self,
        user_id: str = "default",
        mcp=None,
        runner: AgentRunner | None = None,
    ):
        self.user_id = user_id
        self.mcp = mcp
        self.runner = runner or AgentRunner()
        self.system_prompt = self.build_system_prompt()

    def run(self, user_input: str) -> str:
        context = self.build_context(user_input)
        result = self.runner.run(context)
        if result.content:
            save_message(self.user_id, "assistant", result.content)
        return result.content

    def stream(self, user_input: str) -> Iterator[tuple[str, object]]:
        context = self.build_context(user_input)
        final_content = ""

        for event_type, data in self.runner.stream(context):
            if event_type == "final":
                final_content = str(data or "")
                continue
            if event_type == "done":
                if final_content:
                    save_message(self.user_id, "assistant", final_content)
                    final_content = ""
                yield (event_type, data)
                continue
            yield (event_type, data)

        if final_content:
            save_message(self.user_id, "assistant", final_content)

    def build_context(self, user_input: str) -> AgentContext:
        history = load_history(self.user_id)
        save_message(self.user_id, "user", user_input)
        if history:
            print(f"  [记忆加载] 用户 {self.user_id}，读取 {len(history)} 条历史")

        return AgentContext(
            user_id=self.user_id,
            user_input=user_input,
            system_prompt=self.system_prompt,
            history=history,
            tools=TOOLS + (self.mcp.tools if self.mcp else []),
            mcp=self.mcp,
        )

    def build_system_prompt(self) -> str:
        github_username = os.getenv("GITHUB_USERNAME", "unknown")

        soul_file = Path.home() / ".my-agent" / "SOUL.md"
        soul_content = (
            soul_file.read_text(encoding="utf-8").strip() if soul_file.exists() else ""
        )

        memory_file = Path.home() / ".my-agent" / "MEMORY.md"
        memory_content = (
            memory_file.read_text(encoding="utf-8").strip()
            if memory_file.exists()
            else ""
        )

        soul_section = soul_content + "\n\n" if soul_content else ""

        from core.skills import get_skills_loader

        skills_section = get_skills_loader().get_summary_text()
        skills_block = f"\n{skills_section}\n" if skills_section else ""

        memory_block = (
            chr(10)
            + "## Long-term memory about this user"
            + chr(10)
            + memory_content
            + chr(10)
            if memory_content
            else ""
        )

        return f"""{soul_section}You are a helpful AI assistant with access to tools including GitHub, file system, web search, stock prices, and more.

User info:
- GitHub username: {github_username}
{memory_block}{skills_block}
Rules:
- Respond ONLY to the user's latest message. Do not continue or assume tasks from previous messages.
- Only use tools when the current message explicitly requires them. A greeting like "hi" never needs tools.
- When using GitHub tools, always use the username "{github_username}" unless the user explicitly mentions a different account.
- You CAN set reminders using the set_reminder tool. When user says "remind me to X at Y", call set_reminder immediately.
- Always summarize tool results in clear, natural language. Never show raw JSON.
- Answer directly and concisely. No disclaimers."""
