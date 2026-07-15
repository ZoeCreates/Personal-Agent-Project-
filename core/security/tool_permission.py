from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.security.workspace_policy import (
    DENY,
    READ,
    REQUIRE_APPROVAL,
    WRITE,
    PolicyDecision,
    WorkspacePolicy,
    get_workspace_policy,
)

ALLOW = "allow"

APPROVAL_TOOL_HINTS = (
    "delete",
    "remove",
    "move",
    "rename",
    "patch",
)

TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ToolPermissionDecision:
    action: str
    reason: str = ""
    risk: str = "low"

    @property
    def allowed(self) -> bool:
        return self.action == ALLOW

    @property
    def denied(self) -> bool:
        return self.action == DENY

    @property
    def requires_approval(self) -> bool:
        return self.action == REQUIRE_APPROVAL


class ToolPermissionGate:
    """Central pre-execution policy for built-in and MCP tools."""

    def __init__(self, workspace_policy: WorkspacePolicy | None = None):
        self.workspace_policy = workspace_policy or get_workspace_policy()

    def check(self, tool_name: str, args: dict[str, Any]) -> ToolPermissionDecision:
        args = args or {}

        if _env_bool("MY_AGENT_AUTO_APPROVE_TOOLS", False):
            return ToolPermissionDecision(ALLOW, "auto approval enabled")

        if tool_name == "write_file":
            return self._check_write_file(args)

        if tool_name in {"read_file", "list_files"}:
            operation = READ
            path = args.get("path", ".")
            return self._from_workspace_decision(
                self.workspace_policy.check_path(path, operation),
                operation=operation,
                tool_name=tool_name,
            )

        if tool_name.startswith("filesystem__"):
            workspace_decision = self.workspace_policy.check_mcp_tool(tool_name, args)
            if workspace_decision.denied:
                return ToolPermissionDecision(DENY, workspace_decision.reason, "high")
            if self._requires_approval(tool_name):
                return ToolPermissionDecision(
                    REQUIRE_APPROVAL,
                    f"{tool_name} changes filesystem state and needs approval",
                    "high",
                )
            return ToolPermissionDecision(ALLOW)

        if self._requires_approval(tool_name):
            return ToolPermissionDecision(
                REQUIRE_APPROVAL,
                f"{tool_name} is a high-risk tool and needs approval",
                "high",
            )

        return ToolPermissionDecision(ALLOW)

    def _check_write_file(self, args: dict[str, Any]) -> ToolPermissionDecision:
        path = args.get("path")
        if not path:
            return ToolPermissionDecision(DENY, "write_file requires path", "high")

        workspace_decision = self.workspace_policy.check_path(path, WRITE)
        if workspace_decision.denied:
            return ToolPermissionDecision(DENY, workspace_decision.reason, "high")

        target = workspace_decision.path
        overwrite = bool(args.get("overwrite"))
        if overwrite or (target and target.exists()):
            display = _display_path(target)
            return ToolPermissionDecision(
                REQUIRE_APPROVAL,
                f"write_file would overwrite existing file: {display}",
                "medium",
            )

        return ToolPermissionDecision(ALLOW)

    @staticmethod
    def _from_workspace_decision(
        decision: PolicyDecision,
        *,
        operation: str,
        tool_name: str,
    ) -> ToolPermissionDecision:
        if decision.denied:
            return ToolPermissionDecision(DENY, decision.reason, "medium")
        return ToolPermissionDecision(ALLOW, f"{tool_name} {operation} allowed")

    @staticmethod
    def _requires_approval(tool_name: str) -> bool:
        lowered = tool_name.lower()
        return any(hint in lowered for hint in APPROVAL_TOOL_HINTS)


def get_tool_permission_gate() -> ToolPermissionGate:
    return ToolPermissionGate()


def _display_path(path: Path | None) -> str:
    return str(path) if path else "(unknown path)"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUTHY
