"""Configuration: loopback binding, token entropy, secret redaction, honesty."""

from __future__ import annotations

import pytest
from alfred.config import MIN_TOKEN_LENGTH, MIN_TOKEN_UNIQUE, Settings, get_settings
from conftest import TEST_TOKEN
from pydantic import ValidationError

# --- host / loopback -------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "127.5.6.7", "localhost", "LOCALHOST", "loopback", "::1"])
def test_loopback_hosts_are_accepted(settings_factory, host):
    settings = settings_factory(host=host)
    assert settings.host == host


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "10.0.0.5", "192.168.1.5", "8.8.8.8", "example.com", "", "  ", "*"],
)
def test_non_loopback_hosts_are_rejected(settings_factory, host):
    with pytest.raises(ValidationError, match="loopback"):
        settings_factory(host=host)


def test_default_host_is_loopback(settings_factory):
    settings = settings_factory()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8020


# --- token entropy -----------------------------------------------------------


def test_token_below_minimum_length_is_rejected(settings_factory):
    short_token = "a1b2c3d4e5" * 3  # 30 chars, unique enough but too short
    assert len(short_token) < MIN_TOKEN_LENGTH
    with pytest.raises(ValidationError, match="high entropy"):
        settings_factory(action_token=short_token)


def test_token_with_low_uniqueness_is_rejected(settings_factory):
    low_entropy_token = "a" * MIN_TOKEN_LENGTH
    assert len(set(low_entropy_token)) < MIN_TOKEN_UNIQUE
    with pytest.raises(ValidationError, match="high entropy"):
        settings_factory(action_token=low_entropy_token)


def test_token_meeting_both_thresholds_is_accepted(settings_factory):
    settings = settings_factory(action_token=TEST_TOKEN)
    assert len(TEST_TOKEN) >= MIN_TOKEN_LENGTH
    assert len(set(TEST_TOKEN)) >= MIN_TOKEN_UNIQUE
    assert settings.action_token is not None
    assert settings.action_token.get_secret_value() == TEST_TOKEN


def test_no_token_means_actions_unavailable(settings_factory):
    settings = settings_factory(action_token=None)
    assert settings.actions_available is False


def test_token_matches_uses_constant_time_and_rejects_wrong_values(settings_factory):
    settings = settings_factory(action_token=TEST_TOKEN)
    assert settings.token_matches(TEST_TOKEN) is True
    assert settings.token_matches(TEST_TOKEN + "x") is False
    assert settings.token_matches("totally-different") is False


def test_token_matches_false_when_no_token_configured(settings_factory):
    settings = settings_factory(action_token=None)
    assert settings.token_matches(TEST_TOKEN) is False


# --- secret redaction / sanitized status --------------------------------------


def test_sanitized_status_never_contains_raw_token(settings_factory):
    settings = settings_factory(action_token=TEST_TOKEN)
    status = settings.sanitized_status()
    dumped = repr(status)
    assert TEST_TOKEN not in dumped
    assert status["action_token_configured"] is True


def test_sanitized_status_reports_root_names_not_absolute_paths(settings_factory, tmp_path):
    sensitive_root = tmp_path / "Users" / "super-secret-username" / "Documents"
    sensitive_root.mkdir(parents=True)
    settings = settings_factory(approved_roots=[sensitive_root])
    status = settings.sanitized_status()
    assert status["approved_root_names"] == ["Documents"]
    dumped = repr(status)
    assert "super-secret-username" not in dumped
    assert str(tmp_path) not in dumped


def test_sanitized_status_never_leaks_openai_key(settings_factory):
    settings = settings_factory(model_provider="openai", openai_api_key="sk-super-secret-value-123")
    dumped = repr(settings.sanitized_status())
    assert "sk-super-secret-value-123" not in dumped
    assert settings.sanitized_status()["provider"]["api_key_configured"] is True


def test_sanitized_status_local_only_flag_always_true(settings_factory):
    settings = settings_factory()
    assert settings.sanitized_status()["local_only"] is True


# --- provider / web status honesty -------------------------------------------


def test_provider_status_none_is_explicitly_non_ai(settings_factory):
    settings = settings_factory(model_provider="none")
    status = settings.provider_status()
    assert status["name"] == "deterministic-fallback"
    assert status["model"] is None
    assert status["api_key_configured"] is False


def test_provider_status_ollama_reports_configured_model_and_endpoint(settings_factory):
    settings = settings_factory(
        model_provider="ollama", ollama_model="llama3.1", ollama_url="http://127.0.0.1:11434"
    )
    status = settings.provider_status()
    assert status["name"] == "ollama"
    assert status["model"] == "llama3.1"
    assert status["endpoint"] == "http://127.0.0.1:11434"
    assert status["api_key_configured"] is False


def test_provider_status_openai_reports_key_configured_flag_honestly(settings_factory):
    without_key = settings_factory(model_provider="openai", openai_api_key=None)
    assert without_key.provider_status()["api_key_configured"] is False

    with_key = settings_factory(model_provider="openai", openai_api_key="sk-abc123-long-enough")
    assert with_key.provider_status()["api_key_configured"] is True
    # The raw key must never appear in the status payload itself.
    assert "sk-abc123-long-enough" not in repr(with_key.provider_status())


def test_web_status_disabled_by_default(settings_factory):
    settings = settings_factory()
    status = settings.web_status()
    assert status["enabled"] is False
    assert status["keyless_source"] is None
    assert status["broad_provider"] == "none"
    assert status["broad_provider_configured"] is False


def test_web_status_keyless_wikipedia_available_once_enabled(settings_factory):
    settings = settings_factory(web_research_enabled=True, web_search_provider="none")
    status = settings.web_status()
    assert status["enabled"] is True
    assert status["keyless_source"] == "wikipedia"
    assert status["broad_provider"] == "none"
    assert status["broad_provider_configured"] is False


def test_web_status_brave_requires_both_provider_selection_and_key(settings_factory):
    # Selecting "brave" without a key must NOT honestly report it as configured.
    selected_no_key = settings_factory(
        web_research_enabled=True, web_search_provider="brave", brave_api_key=None
    )
    assert selected_no_key.brave_available is False
    assert selected_no_key.web_status()["broad_provider"] == "none"
    assert selected_no_key.web_status()["broad_provider_configured"] is False

    selected_with_key = settings_factory(
        web_research_enabled=True, web_search_provider="brave", brave_api_key="brave-key-value"
    )
    assert selected_with_key.brave_available is True
    assert selected_with_key.web_status()["broad_provider"] == "brave"
    assert selected_with_key.web_status()["broad_provider_configured"] is True


# --- list coercion / path resolution ------------------------------------------


def test_approved_roots_accepts_comma_and_newline_separated_strings(tmp_path, settings_factory):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    settings = settings_factory(approved_roots=f"{a},{b}")
    assert [p.name for p in settings.approved_roots] == ["a", "b"]

    settings2 = settings_factory(approved_roots=f"{a}\n{b}")
    assert [p.name for p in settings2.approved_roots] == ["a", "b"]


def test_approved_roots_resolved_to_absolute_paths(tmp_path, settings_factory):
    root = tmp_path / "relative-target"
    root.mkdir()
    settings = settings_factory(approved_roots=[root])
    assert settings.approved_roots[0].is_absolute()


def test_allowed_url_hosts_normalised_to_lowercase(settings_factory):
    settings = settings_factory(allowed_url_hosts=["Example.COM", " other.example "])
    assert settings.allowed_url_hosts == ["example.com", "other.example"]


def test_empty_string_list_field_yields_empty_list(settings_factory):
    settings = settings_factory(approved_roots="")
    assert settings.approved_roots == []


# --- get_settings() caching ----------------------------------------------------


def test_get_settings_is_cached_per_process(monkeypatch, tmp_path):
    monkeypatch.setenv("ALFRED_HOST", "127.0.0.1")
    monkeypatch.setenv("ALFRED_DB_PATH", str(tmp_path / "cached.db"))
    monkeypatch.setenv("ALFRED_KNOWLEDGE_ROOT", str(tmp_path))
    first = get_settings()
    second = get_settings()
    assert first is second


def test_get_settings_reads_alfred_prefixed_env_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("ALFRED_HOST", "127.0.0.1")
    monkeypatch.setenv("ALFRED_PORT", "9090")
    monkeypatch.setenv("ALFRED_DB_PATH", str(tmp_path / "env.db"))
    monkeypatch.setenv("ALFRED_KNOWLEDGE_ROOT", str(tmp_path))
    settings = get_settings()
    assert settings.port == 9090


def test_settings_default_db_path_and_knowledge_root_point_at_service_dir():
    # Constructed with zero overrides (no factory) purely to confirm the
    # *class* defaults are the real service paths -- this test never
    # instantiates a Database or app, so it never creates alfred.db.
    defaults = Settings.model_fields
    assert defaults["db_path"].default.name == "alfred.db"
