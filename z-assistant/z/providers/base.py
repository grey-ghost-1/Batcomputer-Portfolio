"""Typed reasoning-provider abstraction.

A provider turns a bounded list of structured :class:`Message` objects into a
:class:`CompletionResult`. Providers are async and timeout/cancellation friendly,
report an honest status, and never fabricate model use. The deterministic
fallback is explicitly *not* an AI model.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass
class Message:
    role: Role
    content: str


@dataclass
class CompletionResult:
    text: str
    model_used: bool
    provider: str
    model: str | None
    status: str  # "ok" | "disabled" | "unavailable" | "timeout" | "error"
    detail: str | None = None


@dataclass
class ProviderStatus:
    name: str
    model: str | None
    available: bool
    status: str
    timeout_seconds: float | None
    context_chars: int
    detail: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "available": self.available,
            "status": self.status,
            "timeout_seconds": self.timeout_seconds,
            "context_chars": self.context_chars,
            "detail": self.detail,
        }


@dataclass
class ProviderConfig:
    model: str | None
    endpoint: str | None
    timeout_seconds: float | None
    max_history_messages: int
    max_context_chars: int
    max_response_chars: int
    api_key: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)


def bound_messages(messages: list[Message], config: ProviderConfig) -> list[Message]:
    """Keep the system message, trim history, and cap total context characters."""

    system = [m for m in messages if m.role == "system"]
    rest = [m for m in messages if m.role != "system"]
    if config.max_history_messages >= 0:
        keep = config.max_history_messages if config.max_history_messages else 1
        rest = rest[-keep:]
    trimmed = system + rest

    budget = config.max_context_chars
    out: list[Message] = []
    # Always keep the system message; trim newer-to-older until the budget is spent.
    for message in reversed(trimmed):
        content = message.content
        if message.role != "system" and len(content) > max(0, budget):
            content = content[: max(0, budget)]
        budget -= len(content)
        out.append(Message(role=message.role, content=content))
        if budget <= 0 and message.role != "system":
            break
    out.reverse()
    return out


class ReasoningProvider(abc.ABC):
    name: str = "provider"

    @abc.abstractmethod
    def describe(self) -> ProviderStatus:
        ...

    @abc.abstractmethod
    async def complete(
        self, messages: list[Message], *, max_output_chars: int | None = None
    ) -> CompletionResult:
        ...
