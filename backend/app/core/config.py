"""
Application configuration using Pydantic Settings.
All config values come from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEFAULT_JWT_SECRET = "change-me-in-production-jwt-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
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
        libpq's ``sslmode`` query param, which asyncpg does not understand, and
        drop libpq-only params like ``channel_binding`` (added by Neon) that
        asyncpg rejects outright.
        """
        if not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        parts = urlsplit(v)
        query = [
            ("ssl" if k == "sslmode" else k, val)
            for k, val in parse_qsl(parts.query)
            if k != "channel_binding"
        ]
        return urlunsplit(parts._replace(query=urlencode(query)))

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://:redis_secret@localhost:6379/0"

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
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_MODEL: str = "gpt-4o-mini"
    CLAUDE_MODEL: str = "claude-haiku-4-5"

    # ── RAG chat (see docs/RAG.md) ─────────────────────────────────────────────
    # Gemini only — embeddings never fall back to another provider (vectors aren't comparable).
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    # Fixed by the vector(768) column: another size needs a migration and a full re-index, so
    # any other value is rejected at startup instead of failing on the first insert.
    EMBEDDING_DIM: Literal[768] = 768
    RAG_MAX_FILE_CHARS: int = 100_000      # larger files are skipped (usually generated)
    # Caps embedding cost and memory per index run. 900 keeps one run (plus chat questions) inside
    # Gemini's free tier of 1000 embedded texts/day; raise it on a paid key.
    RAG_MAX_CHUNKS_PER_REPO: int = 900
    RAG_TOP_K: int = 8                     # code chunks put in the prompt
    # Best cosine similarity below this → "low confidence". Measured on this repo (docs/RAG.md):
    # off-topic questions 0.65–0.67, weakest on-topic 0.75.
    RAG_MIN_SIMILARITY: float = 0.70

    # ── JWT ────────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = _DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    @model_validator(mode="after")
    def require_real_secret_in_production(self) -> "Settings":
        """Refuse to boot production with a guessable JWT secret (tokens could be forged)."""
        if self.is_production and (
            self.JWT_SECRET_KEY == _DEFAULT_JWT_SECRET or len(self.JWT_SECRET_KEY) < 32
        ):
            raise ValueError("JWT_SECRET_KEY must be set to a random value of at least 32 characters in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings — call once per process (result is cached)."""
    return Settings()
