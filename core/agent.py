from __future__ import annotations

from dotenv import load_dotenv

from core.loop import AgentLoop
from core.mcp_client import MCPClient

load_dotenv()


class Agent:
    """Compatibility facade used by MessageBus, CLI, Web, and Telegram."""

    def __init__(self, user_id: str = "default", mcp: MCPClient = None):
        self.loop = AgentLoop(user_id=user_id, mcp=mcp)

    @property
    def user_id(self) -> str:
        return self.loop.user_id

    @property
    def mcp(self):
        return self.loop.mcp

    @property
    def llm(self):
        return self.loop.runner.llm

    @property
    def system_prompt(self) -> str:
        return self.loop.system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self.loop.system_prompt = value

    def run(self, user_input: str) -> str:
        return self.loop.run(user_input)

    def stream(self, user_input: str):
        """Generator: yields (type, data) tuples for SSE streaming."""
        yield from self.loop.stream(user_input)
