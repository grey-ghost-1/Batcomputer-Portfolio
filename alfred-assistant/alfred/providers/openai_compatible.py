"""Generic OpenAI-compatible reasoning provider.

Targets any server exposing the OpenAI ``/chat/completions`` contract (for
example LM Studio, llama.cpp, vLLM, or a hosted endpoint). The API key is read
from configuration only — never hardcoded — and is optional for local servers.
The operator chooses the endpoint; SSRF controls apply to the web-research
pipeline, not to this operator-configured model endpoint.
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


class OpenAICompatibleProvider(ReasoningProvider):
    name = "openai-compatible"

    def __init__(self, config: ProviderConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.config = config
        self._transport = transport
        self._base = (config.endpoint or "http://127.0.0.1:1234/v1").rstrip("/")

    def describe(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            model=self.config.model,
            available=True,
            status="configured",
            timeout_seconds=self.config.timeout_seconds,
            context_chars=self.config.max_context_chars,
            detail=f"OpenAI-compatible endpoint at {self._base}",
        )

    async def complete(
        self, messages: list[Message], *, max_output_chars: int | None = None
    ) -> CompletionResult:
        prepared = bound_messages(messages, self.config)
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in prepared],
            "temperature": 0.2,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        headers.update(self.config.extra_headers)

        timeout = httpx.Timeout(self.config.timeout_seconds or 15.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=self._transport, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self._base}/chat/completions", json=payload, headers=headers
                )
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

        choices = (data or {}).get("choices") or []
        text = ""
        if choices:
            text = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
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
