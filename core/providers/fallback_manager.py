from __future__ import annotations


class ProviderFallbackStream:
    """Streaming fallback proxy: retries models/providers at context-enter stage."""

    def __init__(self, manager: "FallbackManager", kwargs: dict):
        self._manager = manager
        self._kwargs = dict(kwargs)
        self._active_cm = None

    def __enter__(self):
        last_error = None

        for model_name in self._manager.models:
            call_kwargs = dict(self._kwargs)
            call_kwargs["model"] = model_name
            if model_name != self._manager.primary_model:
                print(f"  [LLM] 主模型失败，流式切换到 fallback: {model_name}")
            try:
                cm = self._manager.anthropic.stream_with_model(model_name, call_kwargs)
                stream_obj = cm.__enter__()
                self._active_cm = cm
                return stream_obj
            except Exception as e:
                last_error = e
                print(f"  [LLM] 流式模型 {model_name} 调用失败：{e}")

        if self._manager.openai.enabled:
            print(
                f"  [LLM] Anthropic 流式全部失败，切换 OpenAI fallback: {self._manager.openai_model}"
            )
            cm = self._manager.openai.stream_fallback_from_anthropic_kwargs(
                self._kwargs
            )
            stream_obj = cm.__enter__()
            self._active_cm = cm
            return stream_obj

        raise RuntimeError(f"所有流式模型调用失败：{last_error}")

    def __exit__(self, exc_type, exc, tb):
        if self._active_cm is None:
            return False
        return self._active_cm.__exit__(exc_type, exc, tb)


class FallbackManager:
    """Provider-agnostic fallback policy manager."""

    def __init__(
        self, anthropic, openai, primary_model: str, fallback_models: list[str]
    ):
        self.anthropic = anthropic
        self.openai = openai
        self.primary_model = primary_model
        self.openai_model = getattr(openai, "model", "")
        self.models = self._build_models(primary_model, fallback_models)

    @staticmethod
    def _build_models(primary: str, fallbacks: list[str]) -> list[str]:
        # 去重且保持顺序，避免重复尝试同一个模型
        return list(dict.fromkeys([primary] + list(fallbacks)))

    def chat(self, kwargs: dict):
        last_error = None
        for model_name in self.models:
            try:
                call_kwargs = dict(kwargs)
                call_kwargs["model"] = model_name
                if model_name != self.primary_model:
                    print(f"  [LLM] 主模型失败，切换到 fallback: {model_name}")
                return self.anthropic.chat_with_model(model_name, call_kwargs)
            except Exception as e:
                last_error = e
                print(f"  [LLM] 模型 {model_name} 调用失败：{e}")

        if self.openai.enabled:
            print(
                f"  [LLM] Anthropic 全部失败，切换 OpenAI fallback: {self.openai_model}"
            )
            return self.openai.chat_from_anthropic_kwargs(kwargs)

        raise RuntimeError(f"所有模型调用失败：{last_error}")

    def stream(self, kwargs: dict):
        return ProviderFallbackStream(self, kwargs)
