"""
User and UserSettings models.
Users authenticate exclusively through GitHub OAuth — no stored passwords.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base, UUIDMixin, TimestampMixin):
    """
    Represents an authenticated GitHub user.
    GitHub ID is the stable external identifier — login names can change.
    """

    __tablename__ = "users"

    # GitHub identity (never null once created)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    github_login: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    github_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted at rest ideally

    # App-level metadata
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Refresh token (stored hashed)
    refresh_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    settings: Mapped["UserSettings"] = relationship(
        "UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    repositories: Mapped[list["Repository"]] = relationship(  # noqa: F821
        "Repository", back_populates="owner", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(  # noqa: F821
        "Review", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.github_login}>"


class UserSettings(Base, UUIDMixin, TimestampMixin):
    """Per-user preferences. Created automatically on first login."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Review preferences
    default_ai_provider: Mapped[str] = mapped_column(String(20), default="gemini", nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_detail_level: Mapped[str] = mapped_column(String(20), default="detailed", nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="settings")
