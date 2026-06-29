"""
Message Bus — 统一消息中枢
负责跨平台消息的标准化格式和路由
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Iterator


@dataclass
class Message:
    """标准消息格式，所有平台共用这个结构"""

    channel: str  # 来源平台: 'web' | 'telegram' | 'discord' 等
    user_id: str  # 用户 ID（各平台自己定义）
    text: str  # 消息正文
    timestamp: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    metadata: dict = field(default_factory=dict)  # 平台特定的额外信息


@dataclass
class Response:
    """Agent 回复的标准格式"""

    text: str
    channel: str
    user_id: str
    success: bool = True
    error: Optional[str] = None


class MessageBus:
    """
    统一消息中枢
    - 持有一个 Agent 实例池（每个 user_id 一个）
    - 接收标准 Message，调用 Agent，返回 Response
    - 各平台只需调用 process() 或 stream()，不接触 Agent 内部
    """

    def __init__(self, mcp=None):
        from core.agent import Agent

        self._mcp = mcp
        self._agents: dict = {}  # user_id → Agent

    def _get_agent(self, user_id: str):
        """按需创建 Agent（每个用户独立）"""
        from core.agent import Agent

        if user_id not in self._agents:
            self._agents[user_id] = Agent(user_id=user_id, mcp=self._mcp)
        return self._agents[user_id]

    def process(self, message: Message) -> Response:
        """
        同步处理：接收 Message → 返回完整 Response
        适合 Telegram Bot 等非流式场景
        """
        try:
            agent = self._get_agent(message.user_id)
            reply = agent.run(message.text)
            return Response(
                text=reply, channel=message.channel, user_id=message.user_id
            )
        except Exception as e:
            return Response(
                text="抱歉，处理消息时出错，请稍后重试。",
                channel=message.channel,
                user_id=message.user_id,
                success=False,
                error=str(e),
            )

    def stream(self, message: Message) -> Iterator[tuple[str, object]]:
        """
        流式处理：接收 Message → yield (event_type, data) 事件流
        适合 Web SSE 等流式场景
        event_type: 'text' | 'tool' | 'error' | 'done'
        """
        try:
            agent = self._get_agent(message.user_id)
            yield from agent.stream(message.text)
        except Exception as e:
            yield ("error", str(e))
            yield ("done", None)
