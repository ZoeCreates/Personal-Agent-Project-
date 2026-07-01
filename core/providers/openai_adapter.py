from __future__ import annotations

import json

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _ToolUseBlock:
    def __init__(self, tool_call_id, name, input_data):
        self.type = "tool_use"
        self.id = tool_call_id
        self.name = name
        self.input = input_data


class OpenAIResponseAdapter:
    """Wrap OpenAI chat.completions response into Anthropic-like content blocks."""

    def __init__(self, response):
        message = response.choices[0].message
        self.content = []

        text = message.content or ""
        if text:
            self.content.append(_TextBlock(text))

        for tc in message.tool_calls or []:
            raw_args = tc.function.arguments or "{}"
            try:
                parsed_args = json.loads(raw_args)
            except Exception:
                parsed_args = {}
            self.content.append(_ToolUseBlock(tc.id, tc.function.name, parsed_args))


class OpenAIFallbackStream:
    """Wrap one-shot OpenAI response into stream-like context interface."""

    def __init__(self, final_response):
        self._final = final_response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    @property
    def text_stream(self):
        text = ""
        for block in self._final.content:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "")
        if text:
            yield text

    def get_final_message(self):
        return self._final


class OpenAIAdapter:
    """OpenAI-specific conversion and invocation."""

    def __init__(self, api_key: str | None, model: str):
        self.model = model
        self.client = None
        if OpenAI and api_key:
            self.client = OpenAI(api_key=api_key)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _to_openai_messages(self, system: str, messages: list) -> list:
        out = []
        if system:
            out.append({"role": "system", "content": system})

        for m in messages:
            role = m.get("role")
            content = m.get("content", "")

            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue

            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        out.append(
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": block.get("id", "tool_call"),
                                        "type": "function",
                                        "function": {
                                            "name": block.get("name", "unknown"),
                                            "arguments": json.dumps(
                                                block.get("input", {}),
                                                ensure_ascii=False,
                                            ),
                                        },
                                    }
                                ],
                            }
                        )
                    elif btype == "tool_result":
                        out.append(
                            {
                                "role": "tool",
                                "tool_call_id": block.get("tool_use_id", "tool_call"),
                                "content": str(block.get("content", "")),
                            }
                        )

                if text_parts:
                    out.append({"role": role, "content": "\n".join(text_parts)})

        return out

    def _tools_to_openai(self, anthropic_tools: list | None) -> list | None:
        if not anthropic_tools:
            return None
        openai_tools = []
        for t in anthropic_tools:
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": t.get(
                            "input_schema", {"type": "object", "properties": {}}
                        ),
                    },
                }
            )
        return openai_tools

    def chat_from_anthropic_kwargs(self, anthropic_kwargs: dict):
        if not self.enabled:
            raise RuntimeError(
                "OpenAI fallback 不可用：缺少 OPENAI_API_KEY 或 openai SDK"
            )

        system = anthropic_kwargs.get("system", "")
        messages = anthropic_kwargs.get("messages", [])
        openai_messages = self._to_openai_messages(system, messages)

        openai_kwargs = {
            "model": self.model,
            "messages": openai_messages,
        }
        tools = self._tools_to_openai(anthropic_kwargs.get("tools"))
        if tools:
            openai_kwargs["tools"] = tools

        resp = self.client.chat.completions.create(**openai_kwargs)
        return OpenAIResponseAdapter(resp)

    def stream_fallback_from_anthropic_kwargs(self, anthropic_kwargs: dict):
        final = self.chat_from_anthropic_kwargs(anthropic_kwargs)
        return OpenAIFallbackStream(final)
