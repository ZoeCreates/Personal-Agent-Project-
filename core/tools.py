import math
from pathlib import Path

from ddgs import DDGS

from core.security.workspace_policy import READ, WRITE, get_workspace_policy

# 工具注册表
TOOLS = []
TOOL_FUNCTIONS = {}

def register_tool(func):
    """装饰器：注册工具"""
    TOOL_FUNCTIONS[func.__name__] = func
    return func


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _path_display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _policy_denial_message(operation: str, reason: str) -> str:
    return f"文件{operation}被拒绝: {reason}"


# ---- 工具定义 ----

@register_tool
def calculator(expression: str) -> str:
    """计算数学表达式"""
    try:
        result = eval(expression, {"__builtins__": {}}, {"math": math})
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"

@register_tool
def search(query: str) -> str:
    """搜索互联网"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "没有找到相关结果"
        output = ""
        for r in results:
            output += f"标题: {r['title']}\n摘要: {r['body']}\n链接: {r['href']}\n\n"
        return output.strip()
    except Exception as e:
        return f"搜索失败: {e}"

@register_tool
def get_weather(city: str) -> str:
    """获取城市当前天气"""
    try:
        import requests
        res = requests.get(f"https://wttr.in/{city}?format=3", timeout=5)
        return res.text.strip()
    except Exception as e:
        return f"获取天气失败: {e}"

@register_tool
def get_stock_price(symbol: str) -> str:
    """获取股票实时价格"""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol.upper())
        price = ticker.fast_info['last_price']
        return f"{symbol.upper()} 当前价格: ${price:.2f}"
    except Exception as e:
        return f"获取股价失败: {e}"

@register_tool
def get_current_time() -> str:
    """获取当前时间"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@register_tool
def set_reminder(message: str, remind_time: str, user_id: str = "default") -> str:
    """Set a reminder. remind_time must be in format 'YYYY-MM-DD HH:MM'"""
    from core.reminder import save_reminder
    try:
        from datetime import datetime
        datetime.strptime(remind_time, "%Y-%m-%d %H:%M")
    except ValueError:
        return "Invalid time format. Use YYYY-MM-DD HH:MM, e.g. '2026-06-16 09:00'"
    save_reminder(user_id, message, remind_time)
    return f"Reminder set: '{message}' at {remind_time}"

@register_tool
def load_skill(name: str) -> str:
    """Load the full instructions for a named skill from SKILL.md."""
    from core.skills import get_skills_loader

    return get_skills_loader().load_body(name)


@register_tool
def get_notion_todos(status: str = "not_started") -> str:
    """查询 Notion 待办事项。status 可以是 'not_started'(未开始), 'in_progress'(进行中), 'done'(已完成), 'all'(全部)"""
    import requests, os
    from datetime import date

    token = os.getenv("NOTION_TOKEN")
    database_id = "3edf3271-4d3e-839c-a3db-8150e4e472c3"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    status_map = {
        "not_started": "Not started",
        "in_progress": "In progress",
        "done": "Done"
    }

    body = {"page_size": 20}
    if status != "all" and status in status_map:
        body["filter"] = {
            "property": "Status",
            "status": {"equals": status_map[status]}
        }

    res = requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers=headers,
        json=body
    )
    if res.status_code != 200:
        return f"查询失败: {res.text}"

    results = res.json().get("results", [])
    if not results:
        return "没有找到符合条件的待办事项"

    today = str(date.today())
    lines = []
    for page in results:
        props = page.get("properties", {})
        name_list = props.get("Name", {}).get("title", [])
        name = name_list[0]["plain_text"] if name_list else "(无标题)"
        status_obj = props.get("Status", {}).get("status", {})
        status_name = status_obj.get("name", "") if status_obj else ""
        due = props.get("Due date", {}).get("date")
        due_str = due["start"] if due else "无截止日期"
        overdue = " 🥶过期" if due and due["start"] < today and status_name != "Done" else ""
        lines.append(f"- [{status_name}] {name}（截止：{due_str}）{overdue}")

    return "\n".join(lines)


@register_tool
def list_files(path: str = ".", recursive: bool = False, max_entries: int = 100) -> str:
    """List files under an allowed workspace/project path."""
    policy = get_workspace_policy()
    decision = policy.check_path(path, READ)
    if decision.denied:
        return _policy_denial_message("列表读取", decision.reason)

    target = decision.path
    if target is None or not target.exists():
        return f"路径不存在: {path}"

    if target.is_file():
        return _path_display(target, policy.workspace_root)

    max_entries = _clamp(int(max_entries), 1, 500)
    iterator = target.rglob("*") if recursive else target.iterdir()
    entries = []
    skipped = 0

    for child in sorted(iterator, key=lambda item: str(item)):
        child_decision = policy.check_path(child, READ)
        if child_decision.denied:
            skipped += 1
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{_path_display(child, target)}{suffix}")
        if len(entries) >= max_entries:
            break

    if not entries:
        return "没有可读取的文件"

    output = "\n".join(entries)
    notes = []
    if len(entries) >= max_entries:
        notes.append(f"已限制为前 {max_entries} 项")
    if skipped:
        notes.append(f"跳过 {skipped} 个受保护路径")
    if notes:
        output += "\n\n" + "；".join(notes)
    return output


@register_tool
def read_file(path: str, max_chars: int = 12000) -> str:
    """Read a UTF-8 text file after workspace policy validation."""
    policy = get_workspace_policy()
    decision = policy.check_path(path, READ)
    if decision.denied:
        return _policy_denial_message("读取", decision.reason)

    target = decision.path
    if target is None or not target.exists():
        return f"文件不存在: {path}"
    if target.is_dir():
        return f"路径是文件夹，不是文件: {path}"

    max_chars = _clamp(int(max_chars), 1_000, 50_000)
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "读取失败: 只支持 UTF-8 文本文件"
    except OSError as exc:
        return f"读取失败: {exc}"

    if len(content) <= max_chars:
        return content
    return content[:max_chars] + f"\n\n[内容已截断，仅显示前 {max_chars} 字符]"


@register_tool
def write_file(path: str, content: str, overwrite: bool = False) -> str:
    """Write a UTF-8 text file after workspace policy validation."""
    policy = get_workspace_policy()
    decision = policy.check_path(path, WRITE)
    if decision.denied:
        return _policy_denial_message("写入", decision.reason)

    target = decision.path
    if target is None:
        return "写入失败: 无法解析目标路径"
    if target.exists() and not overwrite:
        return "文件已存在，设置 overwrite=true 才会覆盖"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"写入失败: {exc}"

    return f"已写入: {_path_display(target, policy.workspace_root)} ({len(content)} 字符)"

# ---- OpenAI 格式的工具描述 ----

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出允许访问的 workspace/project 路径下的文件。所有路径都会经过 workspace policy 检查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的路径，默认为 workspace 根目录下的当前路径"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出子目录"
                    },
                    "max_entries": {
                        "type": "integer",
                        "description": "最多返回多少项，范围 1-500"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取允许访问的 UTF-8 文本文件。所有路径都会经过 workspace policy 检查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径"
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "最多返回多少字符，范围 1000-50000"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入允许访问的 UTF-8 文本文件。默认不覆盖已有文件，所有路径都会经过 workspace policy 检查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容"
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "文件已存在时是否允许覆盖"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "获取股票实时价格，输入股票代码如 TSLA、AAPL、GOOGL",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "股票代码，例如 TSLA"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "搜索互联网获取实时信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式，例如 '2 + 2' 或 'math.sqrt(16)'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学表达式"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前日期和时间",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a reminder for the user. Use when user says 'remind me', 'set a reminder', 'alert me at', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "What to remind the user about"
                    },
                    "remind_time": {
                        "type": "string",
                        "description": "When to send the reminder, format: YYYY-MM-DD HH:MM"
                    }
                },
                "required": ["message", "remind_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_notion_todos",
            "description": "查询用户的 Notion 待办事项列表。用户问'我有什么todo'、'今天要做什么'、'未完成的任务'等时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["not_started", "in_progress", "done", "all"],
                        "description": "过滤状态：not_started(未开始), in_progress(进行中), done(已完成), all(全部)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": (
                "Load full instructions for a skill by name. "
                "Use when a user task matches an Available skill "
                "(e.g. code-review, research)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name, e.g. code-review",
                    }
                },
                "required": ["name"],
            },
        },
    },
]
