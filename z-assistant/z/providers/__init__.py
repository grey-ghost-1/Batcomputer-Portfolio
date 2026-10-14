"""Provider package: factory that selects the configured reasoning provider."""

from __future__ import annotations

import httpx

from ..config import Settings
from .base import (
    CompletionResult,
    Message,
    ProviderConfig,
    ProviderStatus,
    ReasoningProvider,
    bound_messages,
)
from .fallback import FallbackProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider

__all__ = [
    "CompletionResult",
    "Message",
    "ProviderConfig",
    "ProviderStatus",
    "ReasoningProvider",
    "FallbackProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "bound_messages",
    "build_provider",
]


def build_provider(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> ReasoningProvider:
    """Construct the reasoning provider selected by configuration."""

    if settings.model_provider == "ollama":
        config = ProviderConfig(
            model=settings.ollama_model,
            endpoint=settings.ollama_url,
            timeout_seconds=settings.ollama_timeout_seconds,
            max_history_messages=settings.max_history_messages,
            max_context_chars=settings.max_context_chars,
            max_response_chars=settings.max_response_chars,
        )
        return OllamaProvider(config, transport=transport)
    if settings.model_provider == "openai":
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        config = ProviderConfig(
            model=settings.openai_model,
            endpoint=settings.openai_base_url,
            timeout_seconds=settings.openai_timeout_seconds,
            max_history_messages=settings.max_history_messages,
            max_context_chars=settings.max_context_chars,
            max_response_chars=settings.max_response_chars,
            api_key=api_key,
        )
        return OpenAICompatibleProvider(config, transport=transport)
    config = ProviderConfig(
        model=None,
        endpoint=None,
        timeout_seconds=None,
        max_history_messages=settings.max_history_messages,
        max_context_chars=settings.max_context_chars,
        max_response_chars=settings.max_response_chars,
    )
    return FallbackProvider(config)
