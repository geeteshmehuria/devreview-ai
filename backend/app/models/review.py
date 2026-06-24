"""
Review models — the core of the application.
A Review ties together all findings from a single AI analysis run.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType
from app.models.base import TimestampMixin, UUIDMixin


class ReviewType(StrEnum):
    REPOSITORY = "repository"
    PULL_REQUEST = "pull_request"
    CODE_SNIPPET = "code_snippet"
    FILE_UPLOAD = "file_upload"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Review(Base, UUIDMixin, TimestampMixin):
    """
    Root record for a single AI review run.
    One review → many results, findings, etc.
    Design rationale: keeping Review as the aggregate root lets us paginate
    history efficiently without pulling in all child rows.
    """

    __tablename__ = "reviews"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pull_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pull_requests.id", ondelete="SET NULL"), nullable=True
    )

    review_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=ReviewStatus.PENDING, nullable=False)

    # What was reviewed
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_code: Mapped[str | None] = mapped_column(Text, nullable=True)   # for snippet/file reviews
    file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # AI metadata
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Aggregate scores
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # AI-generated summary (markdown)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Error info if failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="reviews")  # noqa: F821
    repository: Mapped["Repository"] = relationship("Repository", back_populates="reviews")  # noqa: F821
    pull_request: Mapped["PullRequest"] = relationship("PullRequest", back_populates="reviews")  # noqa: F821
    results: Mapped[list["ReviewResult"]] = relationship(
        "ReviewResult", back_populates="review", cascade="all, delete-orphan"
    )
    security_findings: Mapped[list["SecurityFinding"]] = relationship(
        "SecurityFinding", back_populates="review", cascade="all, delete-orphan"
    )
    performance_findings: Mapped[list["PerformanceFinding"]] = relationship(
        "PerformanceFinding", back_populates="review", cascade="all, delete-orphan"
    )
    code_smells: Mapped[list["CodeSmell"]] = relationship(
        "CodeSmell", back_populates="review", cascade="all, delete-orphan"
    )
    technical_debt_items: Mapped[list["TechnicalDebt"]] = relationship(
        "TechnicalDebt", back_populates="review", cascade="all, delete-orphan"
    )


class ReviewResult(Base, UUIDMixin, TimestampMixin):
    """
    Category-level result within a review.
    e.g. Security: 72/100, Performance: 88/100
    """

    __tablename__ = "review_results"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    suggestions: Mapped[list | None] = mapped_column(JSONType, nullable=True)

    review: Mapped["Review"] = relationship("Review", back_populates="results")


class SecurityFinding(Base, UUIDMixin, TimestampMixin):
    """Individual security issue found during a review."""

    __tablename__ = "security_findings"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    cwe_id: Mapped[str | None] = mapped_column(String(50), nullable=True)   # e.g. CWE-89

    review: Mapped["Review"] = relationship("Review", back_populates="security_findings")


class PerformanceFinding(Base, UUIDMixin, TimestampMixin):
    """Performance issue detected during analysis."""

    __tablename__ = "performance_findings"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped["Review"] = relationship("Review", back_populates="performance_findings")


class CodeSmell(Base, UUIDMixin, TimestampMixin):
    """Code quality issues and smells."""

    __tablename__ = "code_smells"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    smell_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refactoring_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped["Review"] = relationship("Review", back_populates="code_smells")


class TechnicalDebt(Base, UUIDMixin, TimestampMixin):
    """Technical debt item with estimated remediation effort."""

    __tablename__ = "technical_debt"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(default=False, nullable=False)

    review: Mapped["Review"] = relationship("Review", back_populates="technical_debt_items")
