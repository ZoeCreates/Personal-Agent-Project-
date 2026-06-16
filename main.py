import asyncio
import os
from dotenv import load_dotenv
from core.agent import Agent
from core.memory import init_db, clear_history
from core.mcp_client import MCPClient

load_dotenv()
init_db()

async def setup_mcp():
    mcp = MCPClient()
    await mcp.connect(
        server_name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/Users/zxia/Desktop"]
    )
    await mcp.connect(
        server_name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_TOKEN")}
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
