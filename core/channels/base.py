"""
Channel 基类 — 所有平台必须实现这个接口
每个 Channel 负责：
1. 把平台消息格式 → 标准 Message 格式
2. 把标准 Response → 发送回给用户
"""

from abc import ABC, abstractmethod
from core.message_bus import Message, Response


class Channel(ABC):
    """所有平台 Channel 的抽象基类"""

    # 平台名称，子类必须覆盖
    name: str = "base"

    @abstractmethod
    def format_incoming(self, raw_data: dict) -> Message:
        """
        把平台原始数据转换为标准 Message

        例如 Telegram 的 update 对象 → Message(channel='telegram', ...)
        例如 Web 的 request.json → Message(channel='web', ...)
        """
        ...

    @abstractmethod
    def send_reply(self, response: Response) -> None:
        """
        把 Agent 回复发送回给用户

        例如 Telegram → bot.send_message(...)
        例如 Web → 写入 SSE 流
        """
        ...
