"""Pull request model — stores GitHub PR metadata for analysis tracking."""

import uuid
from enum import StrEnum

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType
from app.models.base import TimestampMixin, UUIDMixin


class PRStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PullRequest(Base, UUIDMixin, TimestampMixin):
    """A GitHub PR linked to an imported repository."""

    __tablename__ = "pull_requests"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # GitHub metadata
    github_pr_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_login: Mapped[str] = mapped_column(String(255), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=PRStatus.OPEN, nullable=False)
    pr_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Diff metadata
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Risk score from AI review
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cached diff content
    diff_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    files_changed: Mapped[list | None] = mapped_column(JSONType, nullable=True)

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="pull_requests")  # noqa: F821
    reviews: Mapped[list["Review"]] = relationship(  # noqa: F821
        "Review", back_populates="pull_request"
    )
