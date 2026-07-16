from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any
from uuid import uuid4

PENDING = "pending"
DENIED = "denied"
EXECUTED = "executed"
FAILED = "failed"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class ApprovalRequest:
    id: str
    user_id: str
    tool_name: str
    args: dict[str, Any]
    reason: str
    risk: str
    status: str = PENDING
    result: str = ""
    error: str = ""
    created_at: str = field(default_factory=_now)
    decided_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ApprovalStore:
    """In-memory queue for human-approved tool execution."""

    def __init__(self):
        self._items: dict[str, ApprovalRequest] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        user_id: str,
        tool_name: str,
        args: dict[str, Any],
        reason: str,
        risk: str,
    ) -> ApprovalRequest:
        item = ApprovalRequest(
            id=str(uuid4()),
            user_id=user_id,
            tool_name=tool_name,
            args=dict(args or {}),
            reason=reason,
            risk=risk,
        )
        with self._lock:
            self._items[item.id] = item
        return item

    def list(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._items.values())
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        return [item.to_dict() for item in sorted(items, key=lambda item: item.created_at)]

    def get(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._items.get(approval_id)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def deny(self, approval_id: str, reason: str = "") -> ApprovalRequest | None:
        with self._lock:
            item = self._items.get(approval_id)
            if item is None:
                return None
            if item.status != PENDING:
                return item
            item.status = DENIED
            item.error = reason or "Denied by user"
            item.decided_at = _now()
            return item

    def mark_executed(
        self,
        approval_id: str,
        *,
        result: str,
        error: str = "",
    ) -> ApprovalRequest | None:
        with self._lock:
            item = self._items.get(approval_id)
            if item is None:
                return None
            item.status = FAILED if error else EXECUTED
            item.result = result
            item.error = error
            item.decided_at = _now()
            return item


_default_store = ApprovalStore()


def get_approval_store() -> ApprovalStore:
    return _default_store
