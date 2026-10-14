"""Deterministic, explicitly non-AI fallback provider.

This provider never contacts a model. It reports itself as unavailable so the
orchestrator composes a deterministic answer from curated/retrieved context. It
exists so the provider interface is uniform even with no model configured.
"""

from __future__ import annotations

from .base import CompletionResult, Message, ProviderConfig, ProviderStatus, ReasoningProvider


class FallbackProvider(ReasoningProvider):
    name = "deterministic-fallback"

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def describe(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            model=None,
            available=False,
            status="disabled",
            timeout_seconds=None,
            context_chars=self.config.max_context_chars,
            detail="no reasoning model configured; deterministic composition only",
        )

    async def complete(
        self, messages: list[Message], *, max_output_chars: int | None = None
    ) -> CompletionResult:
        return CompletionResult(
            text="",
            model_used=False,
            provider=self.name,
            model=None,
            status="disabled",
            detail="deterministic fallback: no model was used",
        )
