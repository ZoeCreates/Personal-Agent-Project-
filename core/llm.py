import os
from dotenv import load_dotenv
from core.providers.anthropic_adapter import AnthropicAdapter, AnthropicResponse
from core.providers.openai_adapter import OpenAIAdapter
from core.providers.fallback_manager import FallbackManager

load_dotenv()


class LLMClient:
    def __init__(self):
        self.model = os.getenv("MODEL", "claude-sonnet-4-6")
        self.anthropic = AnthropicAdapter(
            api_key=os.getenv("ANTHROPIC_API_KEY"), default_model=self.model
        )
        raw_fallback_models = os.getenv("FALLBACK_MODELS", "claude-3-5-haiku-latest")
        self.fallback_models = [
            m.strip() for m in raw_fallback_models.split(",") if m.strip()
        ]
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai = OpenAIAdapter(
            api_key=os.getenv("OPENAI_API_KEY"), model=self.openai_model
        )
        self.fallback = FallbackManager(
            anthropic=self.anthropic,
            openai=self.openai,
            primary_model=self.model,
            fallback_models=self.fallback_models,
        )

    def chat(self, messages: list, tools: list = None):
        kwargs = self.anthropic.build_kwargs(messages, tools=tools, max_tokens=4096)
        response = self.fallback.chat(kwargs)
        return AnthropicResponse(response)

    def stream_chat(self, messages: list, tools: list = None):
        """Returns a streaming context manager. Use with: with llm.stream_chat(...) as stream"""
        kwargs = self.anthropic.build_kwargs(messages, tools=tools, max_tokens=4096)
        return self.fallback.stream(kwargs)
