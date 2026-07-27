"""
Unified provider interface. Every backend (llama.cpp server, LM Studio,
Ollama, any OpenAI-compatible endpoint) implements this same contract so
the rest of the app never branches on provider type.

All of these providers speak an OpenAI-ish /chat/completions shape in
practice (llama.cpp's server, LM Studio, and Ollama's /v1 compat layer
all do), so a single HTTP-based implementation with per-provider base
URLs/quirks covers them — see openai_compatible.py. Distinct subclasses
exist so provider-specific quirks (e.g. Ollama's native /api/chat as a
fallback) have a clear home instead of accumulating as if-branches.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class GenerationParams:
    temperature: float = 0.8
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.1
    max_tokens: int = 1024
    context_size: int = 8192
    stop: list[str] | None = None


class LLMProvider(ABC):
    """One instance per (provider_type, api_base, model) combination."""

    def __init__(self, api_base: str, model: str, params: GenerationParams | None = None):
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.params = params or GenerationParams()

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Non-streaming completion. Used for the hidden memory-extraction call."""
        raise NotImplementedError

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
    ) -> AsyncIterator[str]:
        """Streaming chat completion for the visible chat reply. Yields text deltas."""
        raise NotImplementedError

    @abstractmethod
    async def list_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError
