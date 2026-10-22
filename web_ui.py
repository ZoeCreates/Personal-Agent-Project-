import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    jsonify,
    Response,
    session,
    stream_with_context,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from core.tools import TOOLS
from pathlib import Path
from dotenv import load_dotenv
from core.memory import init_db, clear_history
from core.message_bus import MessageBus
from core.channels.web import WebChannel
from core.llm import has_llm_credentials
from core.mcp_setup import create_mcp_client
from core.runner import AgentRunner
from core.security.approval_store import PENDING, get_approval_store
from core.security.workspace_policy import get_workspace_policy

load_dotenv()
init_db()

# Ensure static folder path is absolute
static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = Flask(__name__, static_folder=static_folder, static_url_path="/static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# 设置 WEB_PASSWORD 后需要登录；未设置时（本地开发）保持开放
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")
if WEB_PASSWORD:
    # 由密码派生 session 密钥：重启后登录不失效，改密码后旧登录全部失效
    app.secret_key = hashlib.sha256(
        f"my-agent-web-session:{WEB_PASSWORD}".encode()
    ).digest()
    app.config["SESSION_COOKIE_SECURE"] = bool(os.getenv("RAILWAY_ENVIRONMENT"))
else:
    app.secret_key = secrets.token_bytes(32)

LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW_SECONDS = 15 * 60
_login_failures: dict[str, list[float]] = {}

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


@app.context_processor
def inject_auth_flag():
    return {"auth_enabled": bool(WEB_PASSWORD)}


def current_user_id() -> str:
    """每个浏览器一个独立会话；本地无密码模式沿用原来的 web_user。"""
    if not WEB_PASSWORD:
        return "web_user"
    if "uid" not in session:
        session["uid"] = f"web_{secrets.token_hex(8)}"
    return session["uid"]


def _recent_failures(ip: str) -> list[float]:
    cutoff = time.time() - LOGIN_WINDOW_SECONDS
    failures = [t for t in _login_failures.get(ip, []) if t > cutoff]
    _login_failures[ip] = failures
    return failures


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return "/"


@app.before_request
def require_login():
    if not WEB_PASSWORD or session.get("authed"):
        return None
    if request.path == "/login" or request.path.startswith("/static/"):
        return None
    if request.method == "GET" and request.accept_mimetypes.accept_html:
        return redirect(f"/login?next={request.full_path.rstrip('?')}")
    return jsonify({"error": "login required"}), 401


@app.route("/login", methods=["GET", "POST"])
def login():
    if not WEB_PASSWORD:
        return redirect("/")
    next_url = _safe_next(request.values.get("next"))
    if request.method == "GET":
        return render_template("login.html", next_url=next_url, error=None)

    ip = request.remote_addr or "unknown"
    failures = _recent_failures(ip)
    if len(failures) >= LOGIN_MAX_FAILURES:
        return (
            render_template(
                "login.html", next_url=next_url, error="Too many attempts. Try again later."
            ),
            429,
        )

    password = request.form.get("password", "")
    if hmac.compare_digest(password.encode(), WEB_PASSWORD.encode()):
        _login_failures.pop(ip, None)
        session.permanent = True
        session["authed"] = True
        return redirect(next_url)

    failures.append(time.time())
    return (
        render_template("login.html", next_url=next_url, error="Wrong password."),
        401,
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login")


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
        msg = web_channel.format_incoming(
            {"user_id": current_user_id(), "text": user_input}
        )
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

    user_id = current_user_id()

    def generate():
        try:
            msg = web_channel.format_incoming({"user_id": user_id, "text": user_input})
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
    for r in get_due_reminders(user_id=current_user_id()):
        due.append(r["message"])
        mark_sent(r["user_id"], r["message"], r["time"])
    return jsonify({"reminders": due})


@app.route("/clear", methods=["POST"])
def clear():
    user_id = current_user_id()
    clear_history(user_id)
    bus._agents.pop(user_id, None)
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


@app.route("/api/approvals")
def api_approvals():
    status = request.args.get("status") or None
    return jsonify(
        {
            "approvals": get_approval_store().list(
                user_id=current_user_id(),
                status=status,
            )
        }
    )


@app.route("/api/approvals/<approval_id>/deny", methods=["POST"])
def deny_approval(approval_id):
    store = get_approval_store()
    item = store.get(approval_id)
    if item is None:
        return jsonify({"error": "approval not found"}), 404
    if item.user_id != current_user_id():
        return jsonify({"error": "approval does not belong to this user"}), 403
    item = store.deny(approval_id)
    return jsonify({"approval": item.to_dict()})


@app.route("/api/approvals/<approval_id>/approve", methods=["POST"])
def approve_approval(approval_id):
    store = get_approval_store()
    item = store.get(approval_id)
    if item is None:
        return jsonify({"error": "approval not found"}), 404
    if item.user_id != current_user_id():
        return jsonify({"error": "approval does not belong to this user"}), 403
    if item.status != PENDING:
        return jsonify({"approval": item.to_dict()}), 409

    result, trace = AgentRunner.execute_tool_after_approval(
        user_id=item.user_id,
        tool_name=item.tool_name,
        args=item.args,
        mcp=mcp,
    )
    updated = store.mark_executed(
        approval_id,
        result=result,
        error="" if trace.success else result,
    )
    return jsonify({"approval": updated.to_dict() if updated else item.to_dict()})


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json
    github_username = data.get("github_username", "").strip()
    if not github_username:
        return jsonify({"error": "username cannot be empty"}), 400

    # 更新 .env 文件
    # 部署环境没有 .env 文件，此时只更新运行中的值
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
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
