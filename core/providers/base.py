from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Protocol

from core.providers.types import UnifiedRequest, UnifiedResponse


class ProviderStream(Protocol):
    """Normalized stream interface expected by upper layers.

    ProviderStream 是“流式结果长什么样”
    它要求任何流式对象都要提供两件事：

    text_stream：能一段一段吐文本
    get_final_message()：最后能拿到完整结果"""

    @property
    def text_stream(self) -> Iterable[str]: ...

    def get_final_message(self) -> UnifiedResponse: ...


class ProviderStreamContext(Protocol):
    """Context-manager wrapper that yields a ProviderStream.
    ProviderStreamContext 是“流式对象怎么被使用”

    它要求支持 with 这种上下文方式（进入/退出），这样上层代码统一写法，不管底层是 Anthropic 还是 OpenAI。"""

    def __enter__(self) -> ProviderStream: ...

    def __exit__(self, exc_type, exc, tb) -> bool: ...


class BaseProvider(ABC):
    """Provider contract used by the LLM router/fallback manager.
    模型厂商适配器必须实现的方法”
    它强制每个 provider 都实现：

    chat(request)：一次性返回
    stream_chat(request)：流式返回"""

    name: str = "provider"
    supports_tools: bool = True
    supports_stream: bool = True

    # 意思：“你必须实现，不实现就不能实例化”。
    # 所以以后新增 GeminiAdapter、GrokAdapter 时，少写一个方法会立刻报错，不会悄悄埋雷。
    @abstractmethod
    def chat(self, request: UnifiedRequest) -> UnifiedResponse:
        raise NotImplementedError

    @abstractmethod
    def stream_chat(self, request: UnifiedRequest) -> ProviderStreamContext:
        raise NotImplementedError
