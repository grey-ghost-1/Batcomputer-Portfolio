from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

DEVELOPMENT_SECRET = "development-only-change-before-production"
REPOSITORY_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ENV,
        env_prefix="PLATFORM_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "sqlite:///./platform.db"
    database_host: str | None = None
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "batcomputer"
    database_user: str | None = None
    database_password: SecretStr | None = None
    secret_key: str = DEVELOPMENT_SECRET
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    alfred_provider_url: str | None = None
    allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value):
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def assemble_database_connection(self) -> "Settings":
        if self.database_host is None:
            return self
        if not self.database_user or self.database_password is None or not self.database_name:
            raise ValueError(
                "database host configuration requires user, password, and database name"
            )
        self.database_url = URL.create(
            "postgresql+psycopg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        ).render_as_string(hide_password=False)
        return self

    @model_validator(mode="after")
    def production_guards(self) -> "Settings":
        if self.environment == "production":
            if self.secret_key == DEVELOPMENT_SECRET or len(self.secret_key) < 32:
                raise ValueError("production requires a unique secret of at least 32 characters")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("production requires PostgreSQL")
        return self

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
