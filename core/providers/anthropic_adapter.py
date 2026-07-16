from __future__ import annotations

from anthropic import Anthropic

from core.tool_intent import preferred_tool_for_latest_user_message


class AnthropicFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments  # dict


class AnthropicToolCall:
    """Wrap Anthropic tool_use block into OpenAI-like tool_call shape."""

    def __init__(self, block):
        self.id = block.id
        self.function = AnthropicFunction(block.name, block.input)


class AnthropicResponse:
    """Normalize Anthropic response for existing agent consumption."""

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


class AnthropicAdapter:
    """Anthropic-specific request/response conversion and invocation."""

    def __init__(self, api_key: str, default_model: str):
        self.client = Anthropic(api_key=api_key)
        self.default_model = default_model

    def build_kwargs(self, messages: list, tools: list = None, max_tokens: int = 4096):
        system = ""
        filtered = []
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "system":
                system = m["content"]
            else:
                filtered.append(m)

        anthropic_tools = []
        if tools:
            for t in tools:
                f = t["function"]
                anthropic_tools.append(
                    {
                        "name": f["name"],
                        "description": f.get("description", ""),
                        "input_schema": f.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )

        kwargs = {
            "max_tokens": max_tokens,
            "system": system,
            "messages": filtered,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
            preferred_tool = preferred_tool_for_latest_user_message(
                filtered,
                {tool["name"] for tool in anthropic_tools},
            )
            if preferred_tool:
                kwargs["tool_choice"] = {"type": "tool", "name": preferred_tool}
        return kwargs

    def chat_with_model(self, model_name: str, kwargs: dict):
        call_kwargs = dict(kwargs)
        call_kwargs["model"] = model_name or self.default_model
        return self.client.messages.create(**call_kwargs)

    def stream_with_model(self, model_name: str, kwargs: dict):
        call_kwargs = dict(kwargs)
        call_kwargs["model"] = model_name or self.default_model
        return self.client.messages.stream(**call_kwargs)
