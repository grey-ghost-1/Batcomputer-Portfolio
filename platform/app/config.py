from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
