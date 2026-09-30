"""
User model.
Users authenticate exclusively through GitHub OAuth — no stored passwords.
"""

from enum import StrEnum

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base, UUIDMixin, TimestampMixin):
    """
    Represents an authenticated GitHub user.
    GitHub ID is the stable external identifier — login names can change and be reused.
    """

    __tablename__ = "users"

    # GitHub identity (never null once created)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    github_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Fernet-encrypted (see app.core.security.encrypt_secret) — never stored in plaintext
    github_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # App-level metadata
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Refresh token (stored hashed)
    refresh_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships (rows are removed by the DB's ON DELETE CASCADE)
    repositories: Mapped[list["Repository"]] = relationship(  # noqa: F821
        "Repository", back_populates="owner", passive_deletes=True
    )
    reviews: Mapped[list["Review"]] = relationship(  # noqa: F821
        "Review", back_populates="user", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<User {self.github_login}>"
