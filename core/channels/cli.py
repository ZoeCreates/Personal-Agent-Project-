"""
CliChannel — 终端 REPL 适配器
"""

from __future__ import annotations

from core.channels.base import Channel
from core.message_bus import Message, Response


class CliChannel(Channel):
    name = "cli"

    def format_incoming(self, raw_data: dict) -> Message:
        return Message(
            channel=self.name,
            user_id=raw_data.get("user_id", "cli_user"),
            text=raw_data.get("text", ""),
            metadata=raw_data.get("metadata", {}),
        )

    def send_reply(self, response: Response) -> None:
        print(f"Agent: {response.text}\n")
