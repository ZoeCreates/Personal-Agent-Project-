from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class UnifiedToolCall:
    """Provider-agnostic tool call."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedResponse:
    """Provider-agnostic response payload consumed by upper layers."""

    text: Optional[str] = None
    tool_calls: list[UnifiedToolCall] = field(default_factory=list)
    raw: Any = None


@dataclass
class UnifiedRequest:
    """Provider-agnostic request payload passed from router to providers."""

    system: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: Optional[list[dict[str, Any]]] = None
    max_tokens: int = 4096


class ProviderError(RuntimeError):
    """Normalized provider error that keeps category and original error."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        retryable: bool = False,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.cause = cause
