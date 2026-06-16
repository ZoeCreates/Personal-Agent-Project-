import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("MODEL", "claude-sonnet-4-6")

    def chat(self, messages: list, tools: list = None):
        # 把 system message 从 messages 里分离出来
        system = ""
        filtered = []
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "system":
                system = m["content"]
            else:
                filtered.append(m)

        # 转换工具格式（OpenAI → Anthropic）
        anthropic_tools = []
        if tools:
            for t in tools:
                f = t["function"]
                anthropic_tools.append({
                    "name": f["name"],
                    "description": f.get("description", ""),
                    "input_schema": f.get("parameters", {"type": "object", "properties": {}})
                })

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "messages": filtered,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = self.client.messages.create(**kwargs)
        return AnthropicResponse(response)


class AnthropicResponse:
    """把 Anthropic 响应包装成和 OpenAI 一样的接口，让 agent.py 不用改"""
    def __init__(self, response):
        self._response = response
        self.tool_calls = []
        self.content = None

        for block in response.content:
            if block.type == "tool_use":
                self.tool_calls.append(AnthropicToolCall(block))
            elif block.type == "text":
                self.content = block.text

    def __iter__(self):
        return iter(self._response.content)


class AnthropicToolCall:
    """把 Anthropic tool_use block 包装成 OpenAI tool_call 格式"""
    def __init__(self, block):
        self.id = block.id
        self.function = AnthropicFunction(block.name, block.input)


class AnthropicFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments  # 已经是 dict，不是 JSON string
