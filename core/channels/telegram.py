"""
TelegramChannel — Telegram 平台适配器
负责 Telegram Update ↔ 标准 Message/Response 的转换
"""

from core.channels.base import Channel
from core.message_bus import Message, Response


class TelegramChannel(Channel):
    """Telegram Bot 平台的 Channel 实现"""

    name = "telegram"

    def __init__(self):
        self._bot = None  # 延迟绑定，由 telegram_bot.py 设置

    def bind_bot(self, bot):
        """绑定 telegram Bot 实例，用于发送回复"""
        self._bot = bot

    def format_incoming(self, raw_data: dict) -> Message:
        """
        把 Telegram Update 数据转为标准 Message
        raw_data 示例：{'user_id': '123456', 'text': 'hello', 'chat_id': '123456'}
        """
        return Message(
            channel=self.name,
            user_id=str(raw_data.get("user_id", "")),
            text=raw_data.get("text", ""),
            metadata={
                "chat_id": raw_data.get("chat_id", raw_data.get("user_id")),
            },
        )

    def send_reply(self, response: Response) -> None:
        """
        发送回复到 Telegram（同步包装，实际在 telegram_bot.py 中用 await 发送）
        此方法作为接口记录，实际发送逻辑在 telegram_bot.py 的 async handler 中
        """
        pass  # Telegram 回复在 async handler 中 await 发送，不在此处执行
