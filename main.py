import asyncio
import os
from dotenv import load_dotenv
from core.memory import init_db, clear_history
from core.mcp_setup import create_mcp_client
from core.message_bus import MessageBus
from core.channels.cli import CliChannel

load_dotenv()
init_db()

mcp = asyncio.run(create_mcp_client())
bus = MessageBus(mcp=mcp)
cli = CliChannel()
bus.register_channel(cli)

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
        bus._agents.pop("cli_user", None)
        print("历史已清空\n")
        continue

    msg = cli.format_incoming({"user_id": "cli_user", "text": user_input})
    bus.process_and_deliver(msg)
