"""Provider abstraction: bounds, and Ollama/OpenAI-compatible success, timeout,
error, unavailable, and API-key handling -- all via injected MockTransport, no
live network calls.
"""

from __future__ import annotations

import httpx
import pytest
from alfred.providers import (
    FallbackProvider,
    Message,
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    bound_messages,
    build_provider,
)
from conftest import run_async

# --- bound_messages -------------------------------------------------------------


def _config(**overrides):
    defaults = dict(
        model="test-model",
        endpoint="https://example.invalid",
        timeout_seconds=5.0,
        max_history_messages=8,
        max_context_chars=6000,
        max_response_chars=4000,
    )
    defaults.update(overrides)
    return ProviderConfig(**defaults)


def test_bound_messages_always_keeps_the_system_message():
    messages = [Message("system", "SYS"), Message("user", "hi")]
    out = bound_messages(messages, _config(max_history_messages=0))
    assert out[0].role == "system"
    assert out[0].content == "SYS"


def test_bound_messages_trims_history_to_configured_count():
    history = [Message("user", f"turn-{i}") for i in range(10)]
    messages = [Message("system", "SYS"), *history]
    out = bound_messages(messages, _config(max_history_messages=3, max_context_chars=100000))
    non_system = [m for m in out if m.role != "system"]
    assert len(non_system) == 3
    assert non_system[-1].content == "turn-9"


def test_bound_messages_always_keeps_at_least_the_latest_message():
    messages = [Message("system", "SYS"), Message("user", "the actual question")]
    out = bound_messages(messages, _config(max_history_messages=0, max_context_chars=100000))
    non_system = [m for m in out if m.role != "system"]
    assert len(non_system) == 1
    assert non_system[0].content == "the actual question"


def test_bound_messages_caps_total_character_budget():
    messages = [Message("system", "SYS"), Message("user", "x" * 1000)]
    out = bound_messages(messages, _config(max_context_chars=50, max_history_messages=8))
    non_system = [m for m in out if m.role != "system"]
    assert len(non_system[0].content) <= 50


def test_bound_messages_does_not_truncate_the_system_message_for_budget():
    long_system = "S" * 500
    messages = [Message("system", long_system), Message("user", "hi")]
    out = bound_messages(messages, _config(max_context_chars=10))
    assert out[0].content == long_system


# --- fallback provider -----------------------------------------------------------


def test_fallback_provider_reports_unavailable_and_disabled():
    provider = FallbackProvider(_config(model=None, endpoint=None, timeout_seconds=None))
    status = provider.describe()
    assert status.available is False
    assert status.status == "disabled"
    assert status.model is None


def test_fallback_provider_complete_never_uses_a_model():
    provider = FallbackProvider(_config(model=None, endpoint=None, timeout_seconds=None))
    result = run_async(provider.complete([Message("user", "hi")]))
    assert result.model_used is False
    assert result.status == "disabled"
    assert result.text == ""


# --- build_provider factory -------------------------------------------------------


def test_build_provider_selects_fallback_for_none(settings_factory):
    settings = settings_factory(model_provider="none")
    provider = build_provider(settings)
    assert isinstance(provider, FallbackProvider)


def test_build_provider_selects_ollama(settings_factory):
    settings = settings_factory(model_provider="ollama", ollama_model="llama3.1")
    provider = build_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.describe().model == "llama3.1"


def test_build_provider_selects_openai_compatible(settings_factory):
    settings = settings_factory(model_provider="openai", openai_model="local-model")
    provider = build_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.describe().model == "local-model"


# --- Ollama provider ---------------------------------------------------------------


def test_ollama_describe_never_makes_a_network_call():
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("describe() must never touch the network")

    provider = OllamaProvider(_config(), transport=httpx.MockTransport(forbidden))
    status = provider.describe()
    assert status.available is True
    assert status.status == "configured"


def test_ollama_success_returns_model_used_true():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": "Good day."}})

    provider = OllamaProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.model_used is True
    assert result.text == "Good day."
    assert result.status == "ok"


def test_ollama_unavailable_when_connection_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated: server not running", request=request)

    provider = OllamaProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.model_used is False
    assert result.status == "unavailable"


def test_ollama_timeout_is_reported_honestly():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    provider = OllamaProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.model_used is False
    assert result.status == "timeout"


def test_ollama_http_error_status_is_reported_as_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = OllamaProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.model_used is False
    assert result.status == "error"


def test_ollama_non_json_body_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    provider = OllamaProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.status == "error"


def test_ollama_empty_response_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": ""}})

    provider = OllamaProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.status == "error"
    assert result.model_used is False


def test_ollama_truncates_output_to_response_cap():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "x" * 100}})

    provider = OllamaProvider(_config(max_response_chars=10), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")], max_output_chars=10))
    assert len(result.text) <= 11  # 10 chars plus the ellipsis marker
    assert result.text.endswith("\u2026")


def test_ollama_never_sends_more_than_configured_history():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen["messages"] = _json.loads(request.content)["messages"]
        return httpx.Response(200, json={"message": {"content": "ok"}})

    provider = OllamaProvider(
        _config(max_history_messages=1, max_context_chars=100000), transport=httpx.MockTransport(handler)
    )
    history = [Message("system", "SYS")] + [Message("user", f"t{i}") for i in range(5)]
    run_async(provider.complete(history))
    non_system = [m for m in seen["messages"] if m["role"] != "system"]
    assert len(non_system) == 1
    assert non_system[0]["content"] == "t4"


# --- OpenAI-compatible provider -----------------------------------------------------


def test_openai_compatible_success_sends_bearer_header_when_key_configured():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "Very good."}}]})

    provider = OpenAICompatibleProvider(
        _config(api_key="sk-test-key-value"), transport=httpx.MockTransport(handler)
    )
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.model_used is True
    assert result.text == "Very good."
    # The actual outbound header must be a real bearer credential, not a
    # placeholder -- this is what proves the header-construction code is
    # correct end to end (not just plausible-looking source).
    assert captured["auth"] == "Bearer sk-test-key-value"


def test_openai_compatible_omits_authorization_header_without_api_key():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(_config(api_key=None), transport=httpx.MockTransport(handler))
    run_async(provider.complete([Message("user", "hello")]))
    assert captured["auth"] is None


def test_openai_compatible_unavailable_when_connection_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated: endpoint down", request=request)

    provider = OpenAICompatibleProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.status == "unavailable"
    assert result.model_used is False


def test_openai_compatible_timeout_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    provider = OpenAICompatibleProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.status == "timeout"


def test_openai_compatible_http_error_status_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    provider = OpenAICompatibleProvider(
        _config(api_key="wrong-key"), transport=httpx.MockTransport(handler)
    )
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.status == "error"
    assert result.model_used is False


def test_openai_compatible_empty_choices_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider = OpenAICompatibleProvider(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.status == "error"


def test_openai_compatible_extra_headers_are_included():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["custom"] = request.headers.get("x-custom-header")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        _config(extra_headers={"X-Custom-Header": "present"}), transport=httpx.MockTransport(handler)
    )
    run_async(provider.complete([Message("user", "hello")]))
    assert captured["custom"] == "present"


def test_openai_compatible_describe_never_makes_a_network_call():
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("describe() must never touch the network")

    provider = OpenAICompatibleProvider(_config(), transport=httpx.MockTransport(forbidden))
    status = provider.describe()
    assert status.status == "configured"


@pytest.mark.parametrize("provider_cls", [OllamaProvider, OpenAICompatibleProvider])
def test_providers_never_fabricate_model_used_on_failure(provider_cls):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    provider = provider_cls(_config(), transport=httpx.MockTransport(handler))
    result = run_async(provider.complete([Message("user", "hello")]))
    assert result.model_used is False
    assert result.text == ""
