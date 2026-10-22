# My Agent

English | [中文](README.zh-CN.md)

A personal AI assistant built from scratch. One agent core serves a **CLI, a web UI, and a Telegram bot**, with support for multiple LLM providers, tool calling, MCP, long-term memory, scheduled reminders, and pluggable skills. File access and tool calls go through a permission and audit layer.

It also includes an optional local fine-tuning workflow (MLX + QLoRA) that trains a small model on your own chat history so it replies in your voice.

## Features

- **Multiple channels**: CLI (`main.py`), Flask web UI (`web_ui.py`, with streaming output and a settings page), and a Telegram bot (`telegram_bot.py`). All three route to the same agent through a shared `MessageBus`.
- **Multiple providers with fallback**: Anthropic, OpenAI, and any OpenAI-compatible API (Groq, Ollama, etc.). If the primary model fails, the agent retries with each model in `FALLBACK_MODELS`.
- **Built-in tools**: calculator, web search (DuckDuckGo), weather, stock prices (yfinance), current time, reminders, Notion to-dos, and workspace file read/write.
- **MCP**: connects to the filesystem MCP server on startup, and to the GitHub MCP server when `GITHUB_TOKEN` is set.
- **Memory**: per-user conversation history. When history gets long, or after 15 minutes of inactivity, older turns are compressed into a summary (the "Dream" mechanism).
- **Skills**: prompt-based skill packs at `skills/<name>/SKILL.md` (ships with `research` and `code-review`), loaded by the agent on demand.
- **Safety**:
  - File access is limited to configured directories (by default, writes are allowed only in `workspace/`)
  - Tool calls with side effects must be approved in the web UI
  - Every tool call is logged to `~/.my-agent/tool_audit.jsonl`

## Project structure

```
.
├── main.py              # CLI entry point
├── web_ui.py            # Web UI entry point (Flask, port 5001 by default)
├── telegram_bot.py      # Telegram bot entry point
├── core/
│   ├── agent.py         # Agent facade
│   ├── loop.py          # Conversation loop and system prompt
│   ├── runner.py        # Model calls and tool execution
│   ├── llm.py           # Provider selection and fallback
│   ├── providers/       # Anthropic / OpenAI adapters
│   ├── channels/        # CLI / Web / Telegram channels
│   ├── message_bus.py   # Shared message format and routing
│   ├── tools.py         # Built-in tools
│   ├── mcp_client.py    # MCP client
│   ├── memory.py        # Conversation history
│   ├── memory_compressor.py
│   ├── reminder.py      # Scheduled reminders
│   ├── skills.py        # Skill loading
│   ├── tool_audit.py    # Tool call audit log
│   └── security/        # Workspace policy, tool permissions, approvals
├── skills/              # Skill definitions
├── templates/, static/  # Web frontend
├── finetune/            # Optional local fine-tuning (see finetune/README.md)
└── tests/
```

## Getting started

Requires Python 3.10+. Node.js (`npx`) is needed for MCP.

```bash
git clone https://github.com/ZoeCreates/Personal-Agent-Project-.git
cd Personal-Agent-Project-
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add at least one LLM API key
```

Pick an entry point:

```bash
python main.py          # CLI; type "clear" to reset history, "quit" to exit
python web_ui.py        # then open http://localhost:5001
python telegram_bot.py  # requires TELEGRAM_TOKEN in .env
```

## Configuration

Everything is configured through `.env`. See [`.env.example`](.env.example) for the full list. The most common settings:

| Variable | Description |
| --- | --- |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` | Set at least one |
| `LLM_PROVIDER` | `auto` (default) / `anthropic` / `openai` / `groq` / `ollama` |
| `MODEL` | Anthropic model name |
| `OPENAI_MODEL`, `OPENAI_BASE_URL` | Model and endpoint for OpenAI-compatible APIs |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `WEB_PASSWORD` | Password for the web UI; leave empty to keep it open locally |
| `GITHUB_TOKEN` | Optional; enables the GitHub MCP server |
| `NOTION_TOKEN`, `NOTION_DATABASE_ID` | Optional; enable the Notion to-do tool |
| `MY_AGENT_WORKSPACE_ROOT` | Directory the agent can write to; defaults to `./workspace` |

> The Notion to-do tool expects a database with `Name`, `Status`, and `Due date` properties.

## Tests

```bash
MY_AGENT_DISABLE_MCP=1 python -m unittest discover tests
```

## Deployment

The `Dockerfile` runs either app through `start.sh`: the Telegram bot by default, or the web UI (served by gunicorn) when `APP_MODE=web`. On Railway, run them as two services from the same repo:

- **Bot service**: no extra variables. Mount a volume at `/root/.my-agent` so memory and reminders survive redeploys.
- **Web service**: set `APP_MODE=web` and `WEB_PASSWORD`, then generate a public domain. Visitors sign in with the password, and each browser gets its own conversation.

Only one copy of the Telegram bot can poll at a time, so stop the local bot once the deployed one is running.

## Local fine-tuning (optional)

`finetune/` runs 4-bit QLoRA fine-tuning of Qwen3-4B with MLX on Apple Silicon to learn a personal writing style. It uses its own environment, separate from the main project; see [finetune/README.md](finetune/README.md) (in Chinese). Training data, model weights, and adapters are excluded by `.gitignore` and never uploaded.
