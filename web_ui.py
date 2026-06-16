import asyncio
import os
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from core.agent import Agent
from core.memory import init_db, clear_history
from core.mcp_client import MCPClient

load_dotenv()
init_db()

app = Flask(__name__)

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
agent = Agent(user_id="web_user", mcp=mcp)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "empty message"}), 400
    response = agent.run(user_input)
    return jsonify({"reply": response})

@app.route("/clear", methods=["POST"])
def clear():
    clear_history("web_user")
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
