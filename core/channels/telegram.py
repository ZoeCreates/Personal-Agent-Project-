"""
TelegramChannel — Telegram 平台适配器
负责 Telegram Update ↔ 标准 Message/Response 的转换与发送
"""

from __future__ import annotations

import asyncio

from core.channels.base import Channel
from core.message_bus import Message, Response


class TelegramChannel(Channel):
    """Telegram Bot 平台的 Channel 实现"""

    name = "telegram"

    def __init__(self):
        self._bot = None

    def bind_bot(self, bot):
        """绑定 telegram Bot 实例，用于发送回复"""
        self._bot = bot

    def format_incoming(self, raw_data: dict) -> Message:
        chat_id = str(raw_data.get("chat_id", raw_data.get("user_id", "")))
        return Message(
            channel=self.name,
            user_id=str(raw_data.get("user_id", "")),
            text=raw_data.get("text", ""),
            metadata={"chat_id": chat_id},
        )

    async def async_send_reply(self, response: Response) -> None:
        if self._bot is None:
            raise RuntimeError("Telegram bot 未 bind，无法发送回复")
        chat_id = (response.metadata or {}).get("chat_id") or response.user_id
        await self._bot.send_message(chat_id=chat_id, text=response.text)

    def send_reply(self, response: Response) -> None:
        """同步包装：无 running loop 时用 asyncio.run；有 loop 时请用 async_send_reply。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.async_send_reply(response))
            return
        raise RuntimeError(
            "在 async 上下文中请 await TelegramChannel.async_send_reply(response)"
        )
