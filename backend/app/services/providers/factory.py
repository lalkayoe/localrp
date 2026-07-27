from __future__ import annotations

from app.services.providers.base import GenerationParams, LLMProvider
from app.services.providers.ollama import OllamaProvider
from app.services.providers.openai_compatible import OpenAICompatibleProvider


def create_provider(
    provider_type: str,
    api_base: str,
    model: str,
    params: GenerationParams | None = None,
    api_key: str | None = None,
) -> LLMProvider:
    """
    provider_type: "llama_cpp" | "lmstudio" | "openai_compatible" | "ollama"

    llama_cpp, lmstudio, and openai_compatible all use the same HTTP client
    since they all expose /v1/chat/completions — they're kept as distinct
    labels in Settings purely for UI clarity and future provider-specific
    tuning (e.g. llama.cpp-specific sampling params), not because the
    request shape differs today.
    """
    if provider_type == "ollama":
        return OllamaProvider(api_base=api_base, model=model, params=params)
    if provider_type in ("llama_cpp", "lmstudio", "openai_compatible"):
        return OpenAICompatibleProvider(api_base=api_base, model=model, params=params, api_key=api_key)
    raise ValueError(f"Unknown provider_type: {provider_type}")
