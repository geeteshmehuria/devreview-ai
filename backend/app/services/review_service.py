"""
Review orchestration service.
Coordinates: AI provider → DB persistence → cache population.

The AI call happens before any row is written, so no DB transaction is held
open while waiting on the model.
"""

import hashlib
import uuid

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from app.ai import run_review
from app.ai.base import ReviewRequest, ReviewResponse
from app.ai.response_formatter import build_response
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.redis import cache_get, cache_set
from app.models.review import (
    CodeSmell,
    PerformanceFinding,
    Review,
    ReviewResult,
    ReviewStatus,
    ReviewType,
    SecurityFinding,
    TechnicalDebt,
)
from app.schemas.review import CodeReviewRequest

logger = structlog.get_logger()
settings = get_settings()


async def save_review(db: AsyncSession, review: Review, resp: ReviewResponse) -> Review:
    """Mark a review completed and persist every category score and finding from the AI response."""
    review.status = ReviewStatus.COMPLETED
    review.overall_score = resp.overall_score
    review.risk_score = resp.risk_score
    review.ai_summary = resp.ai_summary
    review.ai_provider = resp.provider
    review.ai_model = resp.model
    review.prompt_tokens = resp.prompt_tokens
    review.completion_tokens = resp.completion_tokens
    db.add(review)
    await db.flush()  # assigns review.id

    rid = review.id
    db.add_all(
        [
            ReviewResult(
                review_id=rid, category=cs.category, score=cs.score,
                summary=cs.summary, suggestions=cs.suggestions, details=cs.details,
            )
            for cs in resp.category_scores
        ]
        + [
            SecurityFinding(
                review_id=rid, severity=f.severity, title=f.title, description=f.description,
                file_path=f.file_path, line_number=f.line_number, code_snippet=f.code_snippet,
                recommendation=f.recommendation, cwe_id=_short(f.extra.get("cwe_id"), 50),
            )
            for f in resp.security_findings
        ]
        + [
            PerformanceFinding(
                review_id=rid, severity=f.severity, title=f.title, description=f.description,
                file_path=f.file_path, line_number=f.line_number,
                recommendation=f.recommendation, impact=_short(f.extra.get("impact")),
            )
            for f in resp.performance_findings
        ]
        + [
            CodeSmell(
                review_id=rid, smell_type=f.title[:100], severity=f.severity, description=f.description,
                file_path=f.file_path, line_start=f.line_number, refactoring_suggestion=f.recommendation,
            )
            for f in resp.code_smells
        ]
        + [
            TechnicalDebt(
                review_id=rid, category=(_short(f.extra.get("category"), 100) or "general"),
                severity=f.severity, title=f.title, description=f.description, file_path=f.file_path,
                estimated_hours=_float_or_none(f.extra.get("estimated_hours")),
                recommendation=f.recommendation,
            )
            for f in resp.technical_debt
        ]
    )
    await db.flush()
    return review


async def save_failed_review(db: AsyncSession, review: Review, error: Exception) -> None:
    """Commit a FAILED review so it survives the request's rollback and shows up in history."""
    review.status = ReviewStatus.FAILED
    review.error_message = str(error)[:1000]
    db.add(review)
    await db.commit()
    logger.error("review_failed", review_id=str(review.id), error=str(error))


async def create_code_review(
    db: AsyncSession,
    redis: aioredis.Redis,
    request: CodeReviewRequest,
    user_id: str,
    review_type: str = ReviewType.CODE_SNIPPET,
) -> Review:
    """Run an AI code review (or reuse a cached identical one) and persist all results."""
    review = Review(
        user_id=uuid.UUID(user_id),
        review_type=review_type,
        title=request.filename or f"Code Review — {request.language}",
        language=request.language,
        source_code=request.content,
        file_name=request.filename,
        ai_provider=request.ai_provider or settings.AI_PRIMARY_PROVIDER,
        ai_model="pending",
    )

    cache_key = hashlib.sha256(
        f"{request.language}|{request.detail_level}|{request.ai_provider}|{request.content}".encode()
    ).hexdigest()
    cached = await cache_get(redis, "code_review", cache_key)
    if cached:
        logger.info("review_cache_hit", hash=cache_key[:8])
        resp = build_response(cached["data"], cached["provider"], cached["model"])
    else:
        ai_request = ReviewRequest(
            review_type=review_type,
            content=request.content,
            language=request.language,
            context={"filename": request.filename},
            detail_level=request.detail_level,
        )
        try:
            resp = await run_review(ai_request, request.ai_provider)
        except Exception as e:
            await save_failed_review(db, review, e)
            raise
        await cache_set(
            redis, "code_review",
            {"data": resp.raw_response, "provider": resp.provider, "model": resp.model},
            settings.CACHE_TTL_CODE_REVIEW,
            cache_key,
        )

    if resp.language and resp.language != "unknown":
        review.language = resp.language
    await save_review(db, review, resp)
    logger.info("review_completed", review_id=str(review.id), provider=resp.provider, score=resp.overall_score)
    return review


async def get_review(db: AsyncSession, review_id: uuid.UUID, user_id: uuid.UUID) -> Review:
    """Load a review with all child relationships, verifying ownership."""
    result = await db.execute(
        select(Review)
        .options(
            selectinload(Review.results),
            selectinload(Review.security_findings),
            selectinload(Review.performance_findings),
            selectinload(Review.code_smells),
            selectinload(Review.technical_debt_items),
        )
        .where(Review.id == review_id, Review.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise NotFoundError("Review not found")
    return review


async def list_reviews(
    db: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    review_type: str | None = None,
) -> tuple[list[Review], int]:
    """Paginated review history for a user."""
    query = select(Review).where(Review.user_id == user_id)
    if review_type:
        query = query.where(Review.review_type == review_type)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    result = await db.execute(
        query.order_by(desc(Review.created_at)).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


async def list_technical_debt(db: AsyncSession, user_id: uuid.UUID, limit: int = 500) -> list[tuple[TechnicalDebt, Review]]:
    """Technical-debt items across all of a user's reviews, newest first."""
    result = await db.execute(
        select(TechnicalDebt, Review)
        .join(Review, TechnicalDebt.review_id == Review.id)
        .where(Review.user_id == user_id)
        .order_by(desc(TechnicalDebt.created_at))
        .limit(limit)
    )
    return list(result.tuples().all())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _short(value, max_len: int | None = None) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    return text[:max_len] if max_len else text


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
