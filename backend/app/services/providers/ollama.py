"""
Ollama provider. Uses Ollama's native /api/chat and /api/tags instead of
its OpenAI-compat shim, since options like top_k/repeat_penalty and
streaming NDJSON are first-class there.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.services.providers.base import GenerationParams, LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, api_base: str, model: str, params: GenerationParams | None = None):
        super().__init__(api_base, model, params)

    def _options(self) -> dict:
        return {
            "temperature": self.params.temperature,
            "top_p": self.params.top_p,
            "top_k": self.params.top_k,
            "repeat_penalty": self.params.repeat_penalty,
            "num_predict": self.params.max_tokens,
            "num_ctx": self.params.context_size,
        }

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        options = self._options()
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": options,
        }
        async with httpx.AsyncClient(timeout=settings.provider_request_timeout_seconds) as client:
            resp = await client.post(f"{self.api_base}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": self._options(),
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{self.api_base}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = chunk.get("message", {}).get("content")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(f"{self.api_base}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
            except httpx.HTTPError:
                return []

    async def health_check(self) -> bool:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(f"{self.api_base}/api/tags")
                return resp.status_code == 200
            except httpx.HTTPError:
                return False
