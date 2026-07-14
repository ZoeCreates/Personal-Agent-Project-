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

    def __init__(self, content_blocks: list | None = None, response=None):
        self.content = list(content_blocks or [])
        if response is not None:
            message = response.choices[0].message
            text = message.content or ""
            if text:
                self.content.append(_TextBlock(text))

            for tc in message.tool_calls or []:
                raw_args = tc.function.arguments or "{}"
                try:
                    parsed_args = json.loads(raw_args)
                except Exception:
                    parsed_args = {}
                self.content.append(
                    _ToolUseBlock(tc.id, tc.function.name, parsed_args)
                )


class OpenAIStreamContext:
    """Real OpenAI-compatible streaming with Anthropic-like stream interface."""

    def __init__(self, client, openai_kwargs: dict, adapter: "OpenAIAdapter | None" = None):
        self._client = client
        self._kwargs = dict(openai_kwargs)
        self._adapter = adapter
        self._final: OpenAIResponseAdapter | None = None
        self._started = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def _iter_chunks(self, kwargs: dict):
        if self._adapter is not None:
            return self._adapter._create_with_tool_fallback(kwargs, stream=True)
        return self._client.chat.completions.create(**kwargs, stream=True)

    def _consume(self, kwargs: dict):
        text_parts: list[str] = []
        tool_calls: dict[int, dict] = {}

        try:
            stream = self._iter_chunks(kwargs)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    text_parts.append(delta.content)
                    yield delta.content

                for tc in delta.tool_calls or []:
                    slot = tool_calls.setdefault(
                        tc.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
        except Exception as e:
            is_tool_fail = (
                self._adapter is not None and self._adapter._is_tool_use_failed(e)
            ) or OpenAIAdapter._is_tool_use_failed(e)
            if is_tool_fail and kwargs.get("tools") and not text_parts:
                print(
                    f"  [LLM] tool_use_failed（流式），禁用 tools 重试一次"
                )
                retry_kwargs = dict(kwargs)
                retry_kwargs.pop("tools", None)
                retry_kwargs.pop("tool_choice", None)
                yield from self._consume(retry_kwargs)
                return
            raise

        content = []
        text = "".join(text_parts)
        if text:
            content.append(_TextBlock(text))
        for idx in sorted(tool_calls):
            slot = tool_calls[idx]
            raw_args = slot["arguments"] or "{}"
            try:
                parsed_args = json.loads(raw_args)
            except Exception:
                parsed_args = {}
            content.append(
                _ToolUseBlock(
                    slot["id"] or f"tool_call_{idx}",
                    slot["name"] or "unknown",
                    parsed_args,
                )
            )
        self._final = OpenAIResponseAdapter(content_blocks=content)

    @property
    def text_stream(self):
        self._started = True
        yield from self._consume(self._kwargs)

    def get_final_message(self):
        if self._final is None:
            # Ensure stream was consumed (tool-only replies may yield no text)
            if not self._started:
                for _ in self.text_stream:
                    pass
            if self._final is None:
                self._final = OpenAIResponseAdapter(content_blocks=[])
        return self._final


class OpenAIAdapter:
    """OpenAI-compatible adapter (OpenAI, Groq, Ollama, etc.)."""

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str | None = None,
        label: str = "OpenAI",
    ):
        self.model = model
        self.base_url = base_url
        self.label = label
        self.client = None
        if OpenAI and api_key:
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = OpenAI(**kwargs)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _to_openai_messages(self, system: str, messages: list) -> list:
        out = []
        if system:
            out.append({"role": "system", "content": system})

        def _get(block, key, default=None):
            if isinstance(block, dict):
                return block.get(key, default)
            return getattr(block, key, default)

        for m in messages:
            role = m.get("role")
            content = m.get("content", "")

            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue

            if isinstance(content, list):
                text_parts = []
                for block in content:
                    btype = _get(block, "type")
                    if btype == "text":
                        text_parts.append(_get(block, "text", "") or "")
                    elif btype == "tool_use":
                        out.append(
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": _get(block, "id", "tool_call"),
                                        "type": "function",
                                        "function": {
                                            "name": _get(block, "name", "unknown"),
                                            "arguments": json.dumps(
                                                _get(block, "input", {}) or {},
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
                                "tool_call_id": _get(block, "tool_use_id", "tool_call"),
                                "content": str(_get(block, "content", "")),
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

    def _build_openai_kwargs(self, anthropic_kwargs: dict) -> dict:
        system = anthropic_kwargs.get("system", "")
        messages = anthropic_kwargs.get("messages", [])
        openai_kwargs = {
            "model": self.model,
            "messages": self._to_openai_messages(system, messages),
        }
        tools = self._tools_to_openai(anthropic_kwargs.get("tools"))
        if tools:
            openai_kwargs["tools"] = tools
            openai_kwargs["tool_choice"] = "auto"
        return openai_kwargs

    @staticmethod
    def _is_tool_use_failed(exc: Exception) -> bool:
        body = getattr(exc, "body", None)
        if isinstance(body, dict) and body.get("code") == "tool_use_failed":
            return True
        text = str(exc).lower()
        return "failed to call a function" in text or "tool_use_failed" in text

    def _create_with_tool_fallback(self, openai_kwargs: dict, *, stream: bool = False):
        """Groq/Llama sometimes emits invalid tool XML; retry once without tools."""
        try:
            return self.client.chat.completions.create(**openai_kwargs, stream=stream)
        except Exception as e:
            if not (self._is_tool_use_failed(e) and openai_kwargs.get("tools")):
                raise
            print(
                f"  [LLM] {self.label} tool_use_failed，禁用 tools 重试一次"
            )
            retry_kwargs = dict(openai_kwargs)
            retry_kwargs.pop("tools", None)
            retry_kwargs.pop("tool_choice", None)
            return self.client.chat.completions.create(**retry_kwargs, stream=stream)

    def chat_from_anthropic_kwargs(self, anthropic_kwargs: dict):
        if not self.enabled:
            raise RuntimeError(
                f"{self.label} fallback 不可用：缺少 API key 或 openai SDK"
            )
        openai_kwargs = self._build_openai_kwargs(anthropic_kwargs)
        resp = self._create_with_tool_fallback(openai_kwargs, stream=False)
        return OpenAIResponseAdapter(response=resp)

    def stream_fallback_from_anthropic_kwargs(self, anthropic_kwargs: dict):
        if not self.enabled:
            raise RuntimeError(
                f"{self.label} fallback 不可用：缺少 API key 或 openai SDK"
            )
        openai_kwargs = self._build_openai_kwargs(anthropic_kwargs)
        return OpenAIStreamContext(self.client, openai_kwargs, adapter=self)
