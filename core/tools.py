import math
from ddgs import DDGS

# 工具注册表
TOOLS = []
TOOL_FUNCTIONS = {}

def register_tool(func):
    """装饰器：注册工具"""
    TOOL_FUNCTIONS[func.__name__] = func
    return func

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

# ---- OpenAI 格式的工具描述 ----

TOOLS = [
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
    }
]
