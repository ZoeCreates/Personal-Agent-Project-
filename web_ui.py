import asyncio
import json
import os
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    Response,
    stream_with_context,
)
from core.tools import TOOLS
from pathlib import Path
from dotenv import load_dotenv
from core.memory import init_db, clear_history
from core.message_bus import MessageBus
from core.channels.web import WebChannel
from core.llm import has_llm_credentials
from core.mcp_setup import create_mcp_client
from core.security.workspace_policy import get_workspace_policy

load_dotenv()
init_db()

# Ensure static folder path is absolute
static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = Flask(__name__, static_folder=static_folder, static_url_path="/static")
API_KEY_ERROR_MSG = (
    "Missing LLM credentials. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY "
    "in .env and restart the app."
)


def _is_auth_config_error(exc: Exception) -> bool:
    return "Could not resolve authentication method" in str(exc)


def _sse_payload(event_type: str, data):
    payload = json.dumps({"type": event_type, "data": data})
    return f"data: {payload}\n\n"


mcp = asyncio.run(create_mcp_client())
bus = MessageBus(mcp=mcp)
web_channel = WebChannel()
bus.register_channel(web_channel)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    if not has_llm_credentials():
        return jsonify({"error": API_KEY_ERROR_MSG}), 503

    data = request.get_json(silent=True) or {}
    user_input = data.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "empty message"}), 400
    try:
        msg = web_channel.format_incoming({"user_id": "web_user", "text": user_input})
        result = bus.process(msg)
        bus.deliver(result)
        if not result.success:
            return (
                jsonify({"error": result.error or "Request failed, please try again."}),
                500,
            )
        return jsonify({"reply": result.text})
    except Exception as exc:
        app.logger.exception("Chat request failed")
        if _is_auth_config_error(exc):
            return jsonify({"error": API_KEY_ERROR_MSG}), 503
        return jsonify({"error": "Request failed, please try again."}), 500


@app.route("/chat/stream")
def chat_stream():
    if not has_llm_credentials():

        def missing_key_stream():
            yield _sse_payload("error", API_KEY_ERROR_MSG)
            yield _sse_payload("done", None)

        return Response(
            stream_with_context(missing_key_stream()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    user_input = request.args.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "empty message"}), 400

    def generate():
        try:
            msg = web_channel.format_incoming(
                {"user_id": "web_user", "text": user_input}
            )
            for event_type, data in bus.stream(msg):
                yield _sse_payload(event_type, data)
        except Exception as exc:
            app.logger.exception("Streaming chat request failed")
            if _is_auth_config_error(exc):
                yield _sse_payload("error", API_KEY_ERROR_MSG)
            else:
                yield _sse_payload("error", "Request failed, please try again.")
            yield _sse_payload("done", None)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/reminders/poll")
def reminders_poll():
    from core.reminder import get_due_reminders, mark_sent

    due = []
    for r in get_due_reminders(user_id="web_user"):
        due.append(r["message"])
        mark_sent(r["user_id"], r["message"], r["time"])
    return jsonify({"reminders": due})


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
    return jsonify({"builtin": builtin, "mcp": mcp_tools})


@app.route("/api/workspace-policy")
def api_workspace_policy():
    policy = get_workspace_policy()
    return jsonify(
        {
            "workspace_root": str(policy.workspace_root),
            "read_roots": [str(root) for root in policy.read_roots],
            "write_roots": [str(root) for root in policy.write_roots],
            "restricted_paths": list(policy.restricted_paths()),
            "mcp_filesystem_root": str(policy.mcp_filesystem_root()),
            "restrict_mcp_to_workspace": policy.restrict_mcp_to_workspace,
        }
    )


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
    for agent in bus._agents.values():
        agent.system_prompt = agent.system_prompt.replace(
            agent.system_prompt.split("GitHub username: ")[1].split("\n")[0],
            github_username,
        )

    return jsonify({"status": "ok", "github_username": github_username})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(debug=debug, port=port)
