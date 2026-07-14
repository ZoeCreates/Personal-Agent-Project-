"""
WebChannel — Web/Flask 平台适配器
负责 HTTP request ↔ 标准 Message/Response 的转换
"""

from __future__ import annotations

from core.channels.base import Channel
from core.message_bus import Message, Response


class WebChannel(Channel):
    """Web (Flask) 平台的 Channel 实现"""

    name = "web"

    def __init__(self):
        self.last_response: Response | None = None

    def format_incoming(self, raw_data: dict) -> Message:
        return Message(
            channel=self.name,
            user_id=raw_data.get("user_id", "web_user"),
            text=raw_data.get("text", ""),
            metadata=raw_data.get("metadata", {}),
        )

    def send_reply(self, response: Response) -> None:
        # Flask route 仍会读取 Response；此处记录最近一次回复，统一走 Channel 出站接口。
        self.last_response = response
