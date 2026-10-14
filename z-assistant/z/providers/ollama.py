"""Ollama reasoning provider (primary local provider).

Talks to a local Ollama server's ``/api/chat`` endpoint with a strict timeout and
bounded context. Failures and timeouts are reported honestly and never faked as a
successful model call. ``transport`` is injectable so tests never hit a socket.
"""

from __future__ import annotations

import httpx

from .base import (
    CompletionResult,
    Message,
    ProviderConfig,
    ProviderStatus,
    ReasoningProvider,
    bound_messages,
)


class OllamaProvider(ReasoningProvider):
    name = "ollama"

    def __init__(self, config: ProviderConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.config = config
        self._transport = transport
        self._base = (config.endpoint or "http://127.0.0.1:11434").rstrip("/")

    def describe(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            model=self.config.model,
            available=True,
            status="configured",
            timeout_seconds=self.config.timeout_seconds,
            context_chars=self.config.max_context_chars,
            detail=f"local Ollama at {self._base}",
        )

    async def complete(
        self, messages: list[Message], *, max_output_chars: int | None = None
    ) -> CompletionResult:
        prepared = bound_messages(messages, self.config)
        payload = {
            "model": self.config.model,
            "stream": False,
            "messages": [{"role": m.role, "content": m.content} for m in prepared],
            "options": {"temperature": 0.2},
        }
        timeout = httpx.Timeout(self.config.timeout_seconds or 8.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=self._transport, trust_env=False
            ) as client:
                response = await client.post(f"{self._base}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            return self._failure("timeout", f"model request timed out: {exc.__class__.__name__}")
        except httpx.HTTPError as exc:
            return self._failure("unavailable", f"model unreachable: {exc.__class__.__name__}")

        if response.status_code >= 400:
            return self._failure("error", f"model returned status {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            return self._failure("error", "model returned a non-JSON body")

        text = str(((data or {}).get("message") or {}).get("content") or "").strip()
        if not text:
            return self._failure("error", "model returned an empty response")

        cap = max_output_chars or self.config.max_response_chars
        if len(text) > cap:
            text = text[:cap].rstrip() + "\u2026"
        return CompletionResult(
            text=text,
            model_used=True,
            provider=self.name,
            model=self.config.model,
            status="ok",
        )

    def _failure(self, status: str, detail: str) -> CompletionResult:
        return CompletionResult(
            text="",
            model_used=False,
            provider=self.name,
            model=self.config.model,
            status=status,
            detail=detail,
        )
