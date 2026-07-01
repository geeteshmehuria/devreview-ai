"""
Application configuration using Pydantic Settings.
All config values come from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "DevReview AI"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production-at-least-32-characters"
    # NoDecode stops pydantic-settings from JSON-decoding the env value, so the
    # validator below can accept a plain comma-separated string (as in .env.example).
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ── Database ───────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://devreview:devreview_secret@localhost:5432/devreview_ai"
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_db_url(cls, v: str | None) -> str | None:
        """Make managed-provider URLs work with the async engine.

        Render/Heroku/etc. hand out a sync-driver URL (``postgres://`` or
        ``postgresql://``). The app uses SQLAlchemy's async engine, which
        requires the ``asyncpg`` driver, so rewrite the scheme. Also translate
        libpq's ``sslmode`` query param, which asyncpg does not understand.
        """
        if not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v.replace("sslmode=", "ssl=")

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://:redis_secret@localhost:6379/0"
    REDIS_PASSWORD: str = "redis_secret"

    # Cache TTL (seconds)
    CACHE_TTL_REPO_ANALYSIS: int = 3600
    CACHE_TTL_PR_REVIEW: int = 1800
    CACHE_TTL_CODE_REVIEW: int = 900

    # ── GitHub OAuth ───────────────────────────────────────────────────────────
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_CALLBACK_URL: str = "http://localhost:3000/callback"

    # ── AI Providers ───────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    AI_PRIMARY_PROVIDER: Literal["gemini", "openai", "claude"] = "gemini"

    # ── JWT ────────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Celery ─────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://:redis_secret@localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://:redis_secret@localhost:6379/2"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings — call once per process (result is cached)."""
    return Settings()
