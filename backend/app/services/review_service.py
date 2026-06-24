"""
Review orchestration service.
Coordinates: AI provider → DB persistence → cache population.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from app.ai import get_ai_provider
from app.ai.base import ReviewRequest
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


async def create_code_review(
    db: AsyncSession,
    redis: aioredis.Redis,
    request: CodeReviewRequest,
    user_id: str,
    review_type: str = ReviewType.CODE_SNIPPET,
) -> Review:
    """
    Run an AI code review and persist all results.
    Returns immediately after DB insert (caller can poll status if needed).
    For small snippets this is synchronous; large repos use Celery jobs.
    """
    # Check cache (content hash as cache key)
    content_hash = _content_hash(request.content)
    cached = await cache_get(redis, "code_review", content_hash)
    if cached and not getattr(request, "force_refresh", False):
        logger.info("review_cache_hit", hash=content_hash[:8])
        # We still create a DB record pointing to the cached result
        return await _create_review_from_cache(db, cached, user_id, request, review_type)

    # Create pending review record
    review = Review(
        user_id=uuid.UUID(user_id),
        review_type=review_type,
        status=ReviewStatus.PROCESSING,
        title=request.filename or f"Code Review — {request.language}",
        language=request.language,
        source_code=request.content[:50_000],  # cap at 50k chars stored
        file_name=request.filename,
        ai_provider=settings.AI_PRIMARY_PROVIDER,
        ai_model="pending",
    )
    db.add(review)
    await db.flush()

    try:
        provider = get_ai_provider(request.ai_provider)

        ai_request = ReviewRequest(
            review_type=review_type,
            content=request.content,
            language=request.language,
            context={"filename": request.filename},
            detail_level=request.detail_level,
        )

        ai_response = await provider.review(ai_request)

        # Persist results
        review.status = ReviewStatus.COMPLETED
        review.overall_score = ai_response.overall_score
        review.risk_score = ai_response.risk_score
        review.ai_summary = ai_response.ai_summary
        review.language = ai_response.language
        review.ai_provider = ai_response.provider
        review.ai_model = ai_response.model
        review.prompt_tokens = ai_response.prompt_tokens
        review.completion_tokens = ai_response.completion_tokens

        # Category scores
        for cs in ai_response.category_scores:
            db.add(ReviewResult(
                review_id=review.id,
                category=cs.category,
                score=cs.score,
                summary=cs.summary,
                suggestions=cs.suggestions,
                details=cs.details,
            ))

        # Security findings
        for f in ai_response.security_findings:
            db.add(SecurityFinding(
                review_id=review.id,
                severity=f.severity,
                title=f.title,
                description=f.description,
                file_path=f.file_path,
                line_number=f.line_number,
                code_snippet=f.code_snippet,
                recommendation=f.recommendation,
                cwe_id=f.extra.get("cwe_id"),
            ))

        # Performance findings
        for f in ai_response.performance_findings:
            db.add(PerformanceFinding(
                review_id=review.id,
                severity=f.severity,
                title=f.title,
                description=f.description,
                file_path=f.file_path,
                line_number=f.line_number,
                code_snippet=f.code_snippet,
                recommendation=f.recommendation,
                impact=f.extra.get("impact"),
            ))

        # Code smells
        for f in ai_response.code_smells:
            db.add(CodeSmell(
                review_id=review.id,
                smell_type=f.title,
                severity=f.severity,
                description=f.description,
                file_path=f.file_path,
                line_start=f.line_number,
                refactoring_suggestion=f.recommendation,
            ))

        # Technical debt
        for f in ai_response.technical_debt:
            db.add(TechnicalDebt(
                review_id=review.id,
                category=f.extra.get("category", "general"),
                severity=f.severity,
                title=f.title,
                description=f.description,
                file_path=f.file_path,
                estimated_hours=f.extra.get("estimated_hours"),
                recommendation=f.recommendation,
            ))

        # Cache the raw AI response for repeated identical content
        await cache_set(
            redis, "code_review",
            {"review_id": str(review.id), "response": _serialize_ai_response(ai_response)},
            settings.CACHE_TTL_CODE_REVIEW,
            content_hash,
        )

        logger.info(
            "review_completed",
            review_id=str(review.id),
            provider=ai_response.provider,
            score=ai_response.overall_score,
        )

    except Exception as e:
        review.status = ReviewStatus.FAILED
        review.error_message = str(e)
        logger.error("review_failed", review_id=str(review.id), error=str(e))
        raise

    return review


async def get_review(db: AsyncSession, review_id: str, user_id: str) -> Review:
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
        .where(Review.id == uuid.UUID(review_id), Review.user_id == uuid.UUID(user_id))
    )
    review = result.scalar_one_or_none()
    if not review:
        raise NotFoundError("Review not found")
    return review


async def list_reviews(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    review_type: str | None = None,
) -> tuple[list[Review], int]:
    """Paginated review history for a user."""
    query = select(Review).where(Review.user_id == uuid.UUID(user_id))
    count_query = select(func.count()).select_from(Review).where(Review.user_id == uuid.UUID(user_id))

    if review_type:
        query = query.where(Review.review_type == review_type)
        count_query = count_query.where(Review.review_type == review_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(desc(Review.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    reviews = list(result.scalars().all())
    return reviews, total


# ── Helpers ────────────────────────────────────────────────────────────────────

def _content_hash(content: str) -> str:
    import hashlib
    return hashlib.sha256(content.encode()).hexdigest()


def _serialize_ai_response(resp) -> dict:
    """Convert AI response dataclass to JSON-serializable dict."""
    from dataclasses import asdict
    return asdict(resp)


async def _create_review_from_cache(
    db: AsyncSession, cached: dict, user_id: str, request, review_type: str
) -> Review:
    """Create a lightweight review record that references cached data."""
    cached_resp = cached.get("response", {})
    review = Review(
        user_id=uuid.UUID(user_id),
        review_type=review_type,
        status=ReviewStatus.COMPLETED,
        title=request.filename or f"Code Review — {request.language}",
        language=cached_resp.get("language", request.language),
        file_name=request.filename,
        ai_provider=cached_resp.get("provider", settings.AI_PRIMARY_PROVIDER),
        ai_model=cached_resp.get("model", "cached"),
        overall_score=cached_resp.get("overall_score"),
        risk_score=cached_resp.get("risk_score"),
        ai_summary=cached_resp.get("ai_summary"),
        source_code=request.content[:50_000],
    )
    db.add(review)
    await db.flush()
    return review
