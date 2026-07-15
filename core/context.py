from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Per-turn context built by AgentLoop and consumed by AgentRunner."""

    user_id: str
    user_input: str
    system_prompt: str
    history: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    mcp: Any = None

    @property
    def messages(self) -> list[dict[str, Any]]:
        return (
            [{"role": "system", "content": self.system_prompt}]
            + self.history
            + [{"role": "user", "content": self.user_input}]
        )


@dataclass
class ToolTrace:
    name: str
    args: dict[str, Any]
    result: str
    success: bool = True


@dataclass
class RunnerResult:
    content: str
    tool_traces: list[ToolTrace] = field(default_factory=list)
