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
    }
]
