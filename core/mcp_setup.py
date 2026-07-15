"""Shared MCP client bootstrap for CLI / Web / Telegram."""

from __future__ import annotations

import os

from core.mcp_client import MCPClient
from core.security.workspace_policy import get_workspace_policy


async def create_mcp_client() -> MCPClient:
    policy = get_workspace_policy()
    mcp = MCPClient(policy=policy)
    filesystem_root = policy.filesystem_root()
    await mcp.connect(
        server_name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", filesystem_root],
    )
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        await mcp.connect(
            server_name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
        )
    return mcp
