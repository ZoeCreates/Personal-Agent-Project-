"""Shared MCP client bootstrap for CLI / Web / Telegram."""

from __future__ import annotations

import asyncio
import os

from core.mcp_client import MCPClient
from core.security.workspace_policy import get_workspace_policy

TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUTHY


async def _connect_with_timeout(
    mcp: MCPClient,
    *,
    server_name: str,
    command: str,
    args: list[str],
    env: dict[str, str] | None = None,
) -> None:
    timeout = float(os.getenv("MY_AGENT_MCP_CONNECT_TIMEOUT", "10"))
    try:
        await asyncio.wait_for(
            mcp.connect(server_name=server_name, command=command, args=args, env=env),
            timeout=timeout,
        )
    except Exception as exc:
        print(f"  [MCP] 跳过 {server_name}: {exc}")


async def create_mcp_client() -> MCPClient:
    policy = get_workspace_policy()
    mcp = MCPClient(policy=policy)
    if _env_bool("MY_AGENT_DISABLE_MCP"):
        print("  [MCP] 已禁用 MCP 启动")
        return mcp

    filesystem_root = policy.filesystem_root()
    await _connect_with_timeout(
        mcp,
        server_name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", filesystem_root],
    )
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        await _connect_with_timeout(
            mcp,
            server_name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
        )
    return mcp
