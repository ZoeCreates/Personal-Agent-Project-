import asyncio
import os
from flask import Flask, render_template, request, jsonify
from core.tools import TOOLS
from pathlib import Path
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

@app.route("/settings")
def settings():
    return render_template("settings.html")

@app.route("/api/tools")
def api_tools():
    builtin = [t["function"]["name"] for t in TOOLS]
    mcp_tools = list(mcp.tool_map.keys())
    return jsonify({
        "builtin": builtin,
        "mcp": mcp_tools
    })

@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json
    github_username = data.get("github_username", "").strip()
    if not github_username:
        return jsonify({"error": "username cannot be empty"}), 400

    # 更新 .env 文件
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text().splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.startswith("GITHUB_USERNAME="):
            new_lines.append(f"GITHUB_USERNAME={github_username}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"GITHUB_USERNAME={github_username}")
    env_path.write_text("\n".join(new_lines) + "\n")

    # 更新运行中的 agent system prompt
    os.environ["GITHUB_USERNAME"] = github_username
    agent.system_prompt = agent.system_prompt.replace(
        agent.system_prompt.split("GitHub username: ")[1].split("\n")[0],
        github_username
    )

    return jsonify({"status": "ok", "github_username": github_username})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
