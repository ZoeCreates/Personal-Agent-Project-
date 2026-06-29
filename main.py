import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from core.agent import Agent
from core.memory import init_db, clear_history
from core.mcp_client import MCPClient

load_dotenv()
init_db()


async def setup_mcp():
    mcp = MCPClient()
    desktop_dir = Path.home() / "Desktop"
    filesystem_root = str(desktop_dir if desktop_dir.exists() else Path.cwd())
    github_token = os.getenv("GITHUB_TOKEN")
    await mcp.connect(
        server_name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", filesystem_root],
    )
    if github_token:
        await mcp.connect(
            server_name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
        )
    return mcp


mcp = asyncio.run(setup_mcp())
agent = Agent(user_id="cli_user", mcp=mcp)
print("Agent ready! MCP tools loaded.\n")

while True:
    user_input = input("You: ").strip()
    if not user_input:
        continue
    if user_input.lower() == "quit":
        print("Bye!")
        break
    if user_input.lower() == "clear":
        clear_history("cli_user")
        print("历史已清空\n")
        continue
    response = agent.run(user_input)
    print(f"Agent: {response}\n")
