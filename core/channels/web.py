"""
WebChannel — Web/Flask 平台适配器
负责 HTTP request ↔ 标准 Message/Response 的转换
"""

from core.channels.base import Channel
from core.message_bus import Message, Response


class WebChannel(Channel):
    """Web (Flask) 平台的 Channel 实现"""

    name = "web"

    def format_incoming(self, raw_data: dict) -> Message:
        """
        把 Web 请求数据转为标准 Message
        raw_data 示例：{'user_id': 'web_user', 'text': 'hello'}
        """
        return Message(
            channel=self.name,
            user_id=raw_data.get("user_id", "web_user"),
            text=raw_data.get("text", ""),
            metadata=raw_data.get("metadata", {}),
        )

    def send_reply(self, response: Response) -> None:
        """
        Web 是 request/response 模式，回复通过 Flask route 直接 return
        此方法在 SSE 流式场景下不使用，保留作接口完整性
        """
        pass  # Web 回复由 web_ui.py 的 route 直接 return/yield
