"""Shared MCP client bootstrap for CLI / Web / Telegram."""

from __future__ import annotations

import os
from pathlib import Path

from core.mcp_client import MCPClient


async def create_mcp_client() -> MCPClient:
    mcp = MCPClient()
    desktop_dir = Path.home() / "Desktop"
    filesystem_root = str(desktop_dir if desktop_dir.exists() else Path.cwd())
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
