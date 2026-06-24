"""
Repository and RepositoryHealth models.
A repository belongs to one user and accumulates health snapshots over time.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType
from app.models.base import TimestampMixin, UUIDMixin


class RepositoryStatus(StrEnum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    FAILED = "failed"


class Repository(Base, UUIDMixin, TimestampMixin):
    """
    A GitHub repository imported by a user for analysis.
    We store enough metadata to avoid re-fetching from GitHub on every request.
    """

    __tablename__ = "repositories"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # GitHub metadata
    github_repo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)  # e.g. "owner/repo"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    clone_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_issues: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_private: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Analysis state
    status: Mapped[str] = mapped_column(String(20), default=RepositoryStatus.PENDING, nullable=False)
    last_analyzed_at: Mapped[str | None] = mapped_column(Text, nullable=True)  # ISO datetime string
    analysis_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Cached analysis results (JSONB for flexible schema evolution)
    analysis_summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="repositories")  # noqa: F821
    health_snapshots: Mapped[list["RepositoryHealth"]] = relationship(
        "RepositoryHealth", back_populates="repository", order_by="RepositoryHealth.created_at.desc()"
    )
    pull_requests: Mapped[list["PullRequest"]] = relationship(  # noqa: F821
        "PullRequest", back_populates="repository"
    )
    reviews: Mapped[list["Review"]] = relationship(  # noqa: F821
        "Review", back_populates="repository"
    )

    def __repr__(self) -> str:
        return f"<Repository {self.full_name}>"


class RepositoryHealth(Base, UUIDMixin, TimestampMixin):
    """
    Point-in-time health snapshot for a repository.
    Creating a new snapshot instead of updating-in-place gives us trend data.
    """

    __tablename__ = "repository_health"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Overall score 0-100
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Sub-scores (all 0-100)
    security_score: Mapped[float] = mapped_column(Float, nullable=False)
    performance_score: Mapped[float] = mapped_column(Float, nullable=False)
    maintainability_score: Mapped[float] = mapped_column(Float, nullable=False)
    documentation_score: Mapped[float] = mapped_column(Float, nullable=False)
    complexity_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Detailed breakdown (flexible JSONB)
    breakdown: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # Relationship
    repository: Mapped["Repository"] = relationship("Repository", back_populates="health_snapshots")
