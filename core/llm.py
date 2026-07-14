from __future__ import annotations

import os
from dotenv import load_dotenv

from core.providers.anthropic_adapter import AnthropicAdapter, AnthropicResponse
from core.providers.openai_adapter import OpenAIAdapter
from core.providers.fallback_manager import FallbackManager

load_dotenv()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


def resolve_openai_compat() -> tuple[str | None, str | None, str, str]:
    """Resolve OpenAI-compatible credentials.

    Returns (api_key, base_url, model, label).
    Prefer explicit OPENAI_*; otherwise fall back to GROQ_*.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL")

    if openai_key:
        return (
            openai_key,
            base_url,
            model or "gpt-4o-mini",
            "OpenAI",
        )

    if groq_key:
        return (
            groq_key,
            base_url or GROQ_BASE_URL,
            model or GROQ_DEFAULT_MODEL,
            "Groq",
        )

    return None, base_url, model or "gpt-4o-mini", "OpenAI"


def resolve_primary_backend() -> str:
    """Return 'anthropic' or 'openai' based on LLM_PROVIDER."""
    provider = (os.getenv("LLM_PROVIDER") or "auto").strip().lower()
    if provider in {"openai", "groq", "openai_compat", "ollama"}:
        return "openai"
    if provider == "anthropic":
        return "anthropic"
    # auto: use openai-compat primary when Anthropic key missing
    if not os.getenv("ANTHROPIC_API_KEY") and (
        os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
    ):
        return "openai"
    return "anthropic"


def has_llm_credentials() -> bool:
    return bool(
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("GROQ_API_KEY")
    )


class LLMClient:
    def __init__(self):
        self.model = os.getenv("MODEL", "claude-sonnet-4-6")
        self.primary_backend = resolve_primary_backend()

        anthropic_key = os.getenv("ANTHROPIC_API_KEY") or "unused"
        self.anthropic = AnthropicAdapter(
            api_key=anthropic_key, default_model=self.model
        )
        self.anthropic_enabled = bool(os.getenv("ANTHROPIC_API_KEY"))

        raw_fallback_models = os.getenv("FALLBACK_MODELS", "claude-3-5-haiku-latest")
        self.fallback_models = [
            m.strip() for m in raw_fallback_models.split(",") if m.strip()
        ]

        api_key, base_url, openai_model, label = resolve_openai_compat()
        self.openai_model = openai_model
        self.openai = OpenAIAdapter(
            api_key=api_key,
            model=self.openai_model,
            base_url=base_url,
            label=label,
        )
        self.fallback = FallbackManager(
            anthropic=self.anthropic,
            openai=self.openai,
            primary_model=self.model,
            fallback_models=self.fallback_models,
            primary_backend=self.primary_backend,
            anthropic_enabled=self.anthropic_enabled,
        )
        print(
            f"  [LLM] primary={self.primary_backend} "
            f"model={self.model if self.primary_backend == 'anthropic' else self.openai_model} "
            f"openai_compat={label if self.openai.enabled else 'off'}"
        )

    def chat(self, messages: list, tools: list = None):
        kwargs = self.anthropic.build_kwargs(messages, tools=tools, max_tokens=4096)
        response = self.fallback.chat(kwargs)
        return AnthropicResponse(response)

    def stream_chat(self, messages: list, tools: list = None):
        """Returns a streaming context manager. Use with: with llm.stream_chat(...) as stream"""
        kwargs = self.anthropic.build_kwargs(messages, tools=tools, max_tokens=4096)
        return self.fallback.stream(kwargs)
