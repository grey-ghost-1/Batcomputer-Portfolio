"""Configuration for the Alfred Assistant service.

All settings are validated with pydantic-settings. The service is local-first:
the bind host must resolve to a loopback address, desktop actions are disabled
by default, and the high-entropy action token is stored as a ``SecretStr`` so it
never appears in logs or serialized status output.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
SERVICE_DIR = PACKAGE_DIR.parent
REPOSITORY_ROOT = SERVICE_DIR.parent
SERVICE_ENV = SERVICE_DIR / ".env"

LOOPBACK_HOSTNAMES = {"localhost", "loopback"}
MIN_TOKEN_LENGTH = 32
MIN_TOKEN_UNIQUE = 10


def _is_loopback_host(host: str) -> bool:
    candidate = host.strip()
    if not candidate:
        return False
    if candidate.lower() in LOOPBACK_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return address.is_loopback


def _split_list(value: object) -> object:
    """Allow comma or newline separated strings for list-valued settings."""

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped[0] in "[(":  # allow JSON arrays too
            return value
        return [item.strip() for item in stripped.replace("\n", ",").split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVICE_ENV,
        env_prefix="ALFRED_",
        extra="ignore",
    )

    # --- Networking (local-first) -------------------------------------------
    host: str = "127.0.0.1"
    port: int = Field(default=8020, ge=1, le=65535)

    # --- Local action authentication ----------------------------------------
    action_token: SecretStr | None = None
    desktop_actions_enabled: bool = False
    clipboard_enabled: bool = False

    # --- Filesystem safety --------------------------------------------------
    approved_roots: list[Path] = Field(default_factory=list)
    allowed_executables: list[Path] = Field(default_factory=list)
    allowed_url_hosts: list[str] = Field(default_factory=list)
    max_organize_files: int = Field(default=500, ge=1, le=10000)
    max_organize_total_bytes: int = Field(default=256 * 1024 * 1024, ge=1)
    directory_listing_limit: int = Field(default=200, ge=1, le=5000)

    # --- Proposal lifecycle -------------------------------------------------
    proposal_ttl_seconds: int = Field(default=180, ge=5, le=3600)
    audit_retention_days: int = Field(default=30, ge=1, le=3650)

    # --- Persistence --------------------------------------------------------
    db_path: Path = SERVICE_DIR / "alfred.db"

    # --- Knowledge index ----------------------------------------------------
    knowledge_root: Path = REPOSITORY_ROOT
    knowledge_max_bytes: int = Field(default=512 * 1024, ge=1024, le=8 * 1024 * 1024)

    # --- Optional real reasoning provider (off unless explicitly configured) --
    # Provider abstraction: "none" uses the deterministic non-AI fallback only.
    model_provider: Literal["none", "ollama", "openai"] = "none"
    max_history_messages: int = Field(default=8, ge=0, le=40)
    max_context_chars: int = Field(default=6000, ge=256, le=32000)
    max_response_chars: int = Field(default=4000, ge=64, le=32000)

    # Ollama (primary local provider).
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1"
    ollama_timeout_seconds: float = Field(default=8.0, gt=0, le=120)

    # Generic OpenAI-compatible provider (operator-configured endpoint; no key
    # is ever hardcoded and none is required for local servers such as LM Studio).
    openai_base_url: str = "http://127.0.0.1:1234/v1"
    openai_model: str = "local-model"
    openai_api_key: SecretStr | None = None
    openai_timeout_seconds: float = Field(default=15.0, gt=0, le=120)

    # --- Optional web research pipeline (off unless explicitly enabled) -------
    # When enabled, the keyless Wikipedia source operates out of the box; the
    # broad Brave provider is used only when a key is configured.
    web_research_enabled: bool = False
    web_search_provider: Literal["none", "brave"] = "none"
    brave_api_key: SecretStr | None = None
    web_fetch_timeout_seconds: float = Field(default=6.0, gt=0, le=60)
    web_fetch_max_bytes: int = Field(default=512 * 1024, ge=1024, le=8 * 1024 * 1024)
    web_max_redirects: int = Field(default=3, ge=0, le=10)
    web_max_results: int = Field(default=5, ge=1, le=20)
    web_user_agent: str = "AlfredAssistant/1.0 (+local research; contact operator)"

    @field_validator("approved_roots", "allowed_executables", "allowed_url_hosts", mode="before")
    @classmethod
    def _coerce_list(cls, value: object) -> object:
        return _split_list(value)

    @field_validator("host")
    @classmethod
    def _validate_loopback(cls, value: str) -> str:
        if not _is_loopback_host(value):
            raise ValueError(
                "host must be a loopback address (127.0.0.0/8, ::1, or localhost); "
                "Alfred refuses to bind to a non-loopback interface"
            )
        return value

    @field_validator("action_token")
    @classmethod
    def _validate_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        if len(secret) < MIN_TOKEN_LENGTH or len(set(secret)) < MIN_TOKEN_UNIQUE:
            raise ValueError(
                "action token must be high entropy: at least "
                f"{MIN_TOKEN_LENGTH} characters and {MIN_TOKEN_UNIQUE} unique symbols"
            )
        return value

    @field_validator("allowed_url_hosts")
    @classmethod
    def _normalise_hosts(cls, value: list[str]) -> list[str]:
        return [host.strip().lower() for host in value if host.strip()]

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        self.approved_roots = [Path(root).expanduser().resolve() for root in self.approved_roots]
        self.allowed_executables = [
            Path(item).expanduser().resolve() for item in self.allowed_executables
        ]
        self.knowledge_root = Path(self.knowledge_root).expanduser().resolve()
        return self

    @property
    def actions_available(self) -> bool:
        """Actions can only be authenticated when a token has been configured."""

        return self.action_token is not None

    @property
    def brave_available(self) -> bool:
        return self.web_search_provider == "brave" and self.brave_api_key is not None

    def token_matches(self, candidate: str) -> bool:
        import secrets

        if self.action_token is None:
            return False
        return secrets.compare_digest(self.action_token.get_secret_value(), candidate)

    def provider_status(self) -> dict:
        """Non-secret description of the configured reasoning provider."""

        if self.model_provider == "ollama":
            return {
                "name": "ollama",
                "model": self.ollama_model,
                "endpoint": self.ollama_url,
                "timeout_seconds": self.ollama_timeout_seconds,
                "api_key_configured": False,
            }
        if self.model_provider == "openai":
            return {
                "name": "openai-compatible",
                "model": self.openai_model,
                "endpoint": self.openai_base_url,
                "timeout_seconds": self.openai_timeout_seconds,
                "api_key_configured": self.openai_api_key is not None,
            }
        return {
            "name": "deterministic-fallback",
            "model": None,
            "endpoint": None,
            "timeout_seconds": None,
            "api_key_configured": False,
        }

    def web_status(self) -> dict:
        broad = "brave" if self.brave_available else "none"
        return {
            "enabled": self.web_research_enabled,
            "keyless_source": "wikipedia" if self.web_research_enabled else None,
            "broad_provider": broad,
            "broad_provider_configured": self.brave_available,
            "max_results": self.web_max_results,
            "fetch_timeout_seconds": self.web_fetch_timeout_seconds,
            "fetch_max_bytes": self.web_fetch_max_bytes,
        }

    def sanitized_status(self) -> dict:
        """A status view that never leaks the token or absolute machine paths."""

        return {
            "host": self.host,
            "port": self.port,
            "local_only": True,
            "desktop_actions_enabled": self.desktop_actions_enabled,
            "clipboard_enabled": self.clipboard_enabled,
            "action_token_configured": self.action_token is not None,
            "approved_root_count": len(self.approved_roots),
            "approved_root_names": [root.name for root in self.approved_roots],
            "allowed_executable_count": len(self.allowed_executables),
            "allowed_url_host_count": len(self.allowed_url_hosts),
            "allowed_url_hosts": list(self.allowed_url_hosts),
            "proposal_ttl_seconds": self.proposal_ttl_seconds,
            "audit_retention_days": self.audit_retention_days,
            "max_organize_files": self.max_organize_files,
            "max_organize_total_bytes": self.max_organize_total_bytes,
            "provider": self.provider_status(),
            "web": self.web_status(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
