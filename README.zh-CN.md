# My Agent

[English](README.md) | 中文

一个自己从零搭建的个人 AI 助手。同一套 Agent 核心同时接入**命令行、Web 界面和 Telegram Bot**，支持多家大模型、工具调用、MCP、长期记忆、定时提醒和可插拔的 Skills，并带有一套文件/工具权限控制与审计机制。

另附一个可选的本地微调流程（MLX + QLoRA），用自己的聊天记录训练一个“说话像我”的小模型。

## 功能

- **多入口**：CLI（`main.py`）、Flask Web UI（`web_ui.py`，支持流式输出和设置页）、Telegram Bot（`telegram_bot.py`）。三者通过统一的 `MessageBus` 路由到同一个 Agent。
- **多模型 + 自动降级**：支持 Anthropic、OpenAI，以及任意 OpenAI 兼容接口（Groq、Ollama 等）。主模型失败时按 `FALLBACK_MODELS` 依次重试。
- **内置工具**：计算器、联网搜索（DuckDuckGo）、天气、股价（yfinance）、当前时间、定时提醒、Notion 待办查询、工作区文件读写。
- **MCP**：启动时自动连接 filesystem MCP server；配置了 `GITHUB_TOKEN` 时再连接 GitHub MCP server。
- **记忆**：每个用户独立保存会话历史；历史过长或空闲 15 分钟后自动压缩成摘要（“Dream” 机制）。
- **Skills**：`skills/<name>/SKILL.md` 形式的提示词技能包（自带 `research`、`code-review`），Agent 按需加载。
- **安全**：
  - 文件读写限制在指定目录内（默认只允许写 `workspace/`）
  - 有副作用的工具调用需要在 Web 界面上批准
  - 所有工具调用记录到审计日志 `~/.my-agent/tool_audit.jsonl`

## 项目结构

```
.
├── main.py              # 命令行入口
├── web_ui.py            # Web 界面入口（Flask，默认端口 5001）
├── telegram_bot.py      # Telegram Bot 入口
├── core/
│   ├── agent.py         # Agent 门面
│   ├── loop.py          # 对话循环、系统提示词
│   ├── runner.py        # 模型调用 + 工具调用执行
│   ├── llm.py           # 模型选择与降级
│   ├── providers/       # Anthropic / OpenAI 适配器
│   ├── channels/        # CLI / Web / Telegram 渠道
│   ├── message_bus.py   # 统一消息格式与路由
│   ├── tools.py         # 内置工具
│   ├── mcp_client.py    # MCP 客户端
│   ├── memory.py        # 会话历史
│   ├── memory_compressor.py
│   ├── reminder.py      # 定时提醒
│   ├── skills.py        # Skills 加载
│   ├── tool_audit.py    # 工具调用审计
│   └── security/        # 工作区策略、工具权限、审批
├── skills/              # Skill 定义
├── templates/, static/  # Web 前端
├── finetune/            # 可选：本地微调（见 finetune/README.md）
└── tests/
```

## 快速开始

需要 Python 3.10+。如果要用 MCP，还需要 Node.js（`npx`）。

```bash
git clone https://github.com/ZoeCreates/Personal-Agent-Project-.git
cd Personal-Agent-Project-
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 然后填入至少一个模型的 API Key
```

选择一个入口运行：

```bash
python main.py          # 命令行；输入 clear 清空历史，quit 退出
python web_ui.py        # 浏览器打开 http://localhost:5001
python telegram_bot.py  # 需要在 .env 中设置 TELEGRAM_TOKEN
```

## 配置

所有配置都通过 `.env` 设置，完整列表见 [`.env.example`](.env.example)。最常用的几个：

| 变量 | 说明 |
| --- | --- |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` | 至少填一个 |
| `LLM_PROVIDER` | `auto`（默认）/ `anthropic` / `openai` / `groq` / `ollama` |
| `MODEL` | Anthropic 模型名 |
| `OPENAI_MODEL`, `OPENAI_BASE_URL` | OpenAI 兼容接口的模型和地址 |
| `TELEGRAM_TOKEN` | Telegram Bot token |
| `GITHUB_TOKEN` | 可选，启用 GitHub MCP |
| `NOTION_TOKEN`, `NOTION_DATABASE_ID` | 可选，启用 Notion 待办工具 |
| `MY_AGENT_WORKSPACE_ROOT` | Agent 可写入的目录，默认 `./workspace` |

> Notion 待办工具要求数据库包含 `Name`、`Status` 和 `Due date` 三个属性。

## 测试

```bash
MY_AGENT_DISABLE_MCP=1 python -m unittest discover tests
```

## 部署

仓库里的 `Procfile` 把 Telegram Bot 定义为 worker 进程，可以直接部署到 Railway、Heroku 等平台，在平台上配置好环境变量即可。

## 本地微调（可选）

`finetune/` 目录用 MLX 在 Apple Silicon 上对 Qwen3-4B 做 4-bit QLoRA 微调，让模型学习个人说话风格。环境与主项目隔离，步骤见 [finetune/README.md](finetune/README.md)。训练数据、模型权重和 adapter 均已被 `.gitignore` 排除，不会上传。
