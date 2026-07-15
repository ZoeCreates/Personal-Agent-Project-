from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


READ = "read"
WRITE = "write"
REQUIRE_APPROVAL = "require_approval"
DENY = "deny"

PATH_KEYS = {
    "path",
    "paths",
    "file",
    "files",
    "filepath",
    "file_path",
    "filename",
    "source",
    "destination",
    "target",
}

WRITE_TOOL_HINTS = (
    "write",
    "edit",
    "create",
    "delete",
    "remove",
    "move",
    "rename",
    "patch",
    "mkdir",
)


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    reason: str = ""
    path: Path | None = None

    @property
    def allowed(self) -> bool:
        return self.action == "allow"

    @property
    def denied(self) -> bool:
        return self.action == DENY


class WorkspacePolicy:
    """Central path policy for filesystem, MCP filesystem, and future file tools."""

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        project_root: Path | str | None = None,
        read_roots: Iterable[Path | str] | None = None,
        write_roots: Iterable[Path | str] | None = None,
    ):
        self.project_root = self._resolve_dir(project_root or Path.cwd())
        self.workspace_root = self._resolve_dir(
            workspace_root or os.getenv("MY_AGENT_WORKSPACE_ROOT") or self.project_root / "workspace"
        )
        self.read_roots = tuple(
            self._resolve_dir(p) for p in (read_roots or (self.project_root, self.workspace_root))
        )
        self.write_roots = tuple(
            self._resolve_dir(p) for p in (write_roots or (self.workspace_root,))
        )

    def ensure_workspace(self) -> Path:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        return self.workspace_root

    def filesystem_root(self) -> str:
        return str(self.ensure_workspace())

    def check_path(
        self,
        path: str | Path,
        operation: str = READ,
        *,
        base_dir: str | Path | None = None,
    ) -> PolicyDecision:
        resolved = self.resolve_path(path, base_dir=base_dir)

        sensitive_reason = self._sensitive_reason(resolved)
        if sensitive_reason:
            return PolicyDecision(DENY, sensitive_reason, resolved)

        roots = self.write_roots if operation == WRITE else self.read_roots
        if self._is_under_any(resolved, roots):
            return PolicyDecision("allow", path=resolved)

        root_text = ", ".join(str(r) for r in roots)
        return PolicyDecision(
            DENY,
            f"{operation} path is outside allowed roots: {root_text}",
            resolved,
        )

    def check_mcp_tool(self, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
        if not tool_name.startswith("filesystem__"):
            return PolicyDecision("allow")

        for raw_path in self._iter_path_values(args):
            resolved = self.resolve_path(raw_path, base_dir=self.workspace_root)
            sensitive_reason = self._sensitive_reason(resolved)
            if sensitive_reason:
                return PolicyDecision(DENY, sensitive_reason, resolved)
            if not self._is_under_any(resolved, (self.workspace_root,)):
                return PolicyDecision(
                    DENY,
                    f"MCP filesystem path is outside workspace root: {self.workspace_root}",
                    resolved,
                )
        return PolicyDecision("allow")

    def resolve_path(self, path: str | Path, *, base_dir: str | Path | None = None) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(base_dir or self.workspace_root) / candidate
        return candidate.resolve(strict=False)

    @staticmethod
    def _resolve_dir(path: str | Path) -> Path:
        return Path(path).expanduser().resolve(strict=False)

    @staticmethod
    def _is_write_tool(tool_name: str) -> bool:
        lowered = tool_name.lower()
        return any(hint in lowered for hint in WRITE_TOOL_HINTS)

    def _iter_path_values(self, value: Any, *, key: str | None = None):
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                yield from self._iter_path_values(child_value, key=str(child_key))
            return

        if isinstance(value, list):
            for item in value:
                yield from self._iter_path_values(item, key=key)
            return

        if key and key.lower() in PATH_KEYS and isinstance(value, (str, Path)):
            yield value

    @staticmethod
    def _is_under_any(path: Path, roots: Iterable[Path]) -> bool:
        return any(path == root or root in path.parents for root in roots)

    def _sensitive_reason(self, path: Path) -> str:
        home = Path.home().resolve(strict=False)
        sensitive_exact = {
            self.project_root / ".env",
            home / ".ssh",
            home / ".my-agent" / "config",
            home / ".my-agent" / "config.json",
        }
        for sensitive in sensitive_exact:
            sensitive = sensitive.resolve(strict=False)
            if path == sensitive or sensitive in path.parents:
                return f"access to sensitive path is denied: {sensitive}"

        sensitive_parts = {".git", ".ssh"}
        if any(part in sensitive_parts for part in path.parts):
            return "access to git metadata or SSH secrets is denied"
        if path.name == ".env" or path.suffix == ".pem" or path.suffix == ".key":
            return "access to secret-looking files is denied"
        return ""


_default_policy: WorkspacePolicy | None = None


def get_workspace_policy() -> WorkspacePolicy:
    global _default_policy
    if _default_policy is None:
        _default_policy = WorkspacePolicy()
    return _default_policy
