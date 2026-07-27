"""
HTTP provider for any server exposing an OpenAI-compatible
/v1/chat/completions endpoint. This covers, unmodified:

- llama.cpp's built-in server (./llama-server ...)
- LM Studio's local server
- Any hosted-or-local OpenAI-compatible API (vLLM, text-generation-webui
  with the openai extension, etc.)

Ollama is handled by a thin subclass (ollama.py) that mostly reuses this
but talks to /api/chat natively for better tool/format support, since
its OpenAI-compat layer historically lags its native API.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.services.providers.base import GenerationParams, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, api_base: str, model: str, params: GenerationParams | None = None, api_key: str | None = None):
        super().__init__(api_base, model, params)
        self.api_key = api_key

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else self.params.temperature,
            "top_p": self.params.top_p,
            "max_tokens": max_tokens if max_tokens is not None else self.params.max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=settings.provider_request_timeout_seconds) as client:
            resp = await client.post(f"{self.api_base}/v1/chat/completions", json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.params.temperature,
            "top_p": self.params.top_p,
            "max_tokens": self.params.max_tokens,
            "stream": True,
        }
        # NOTE: top_k / repeat_penalty are non-standard OpenAI fields but llama.cpp
        # and LM Studio both accept them passed through directly.
        payload["top_k"] = self.params.top_k
        payload["repeat_penalty"] = self.params.repeat_penalty
        if self.params.stop:
            payload["stop"] = self.params.stop

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{self.api_base}/v1/chat/completions", json=payload, headers=self._headers()) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(f"{self.api_base}/v1/models", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
            except httpx.HTTPError:
                return []

    async def health_check(self) -> bool:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(f"{self.api_base}/v1/models", headers=self._headers())
                return resp.status_code == 200
            except httpx.HTTPError:
                return False
