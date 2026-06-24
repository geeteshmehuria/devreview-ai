"""Review router — code review endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis import get_redis
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.review import ReviewType
from app.schemas.review import (
    CodeReviewRequest,
    ReviewListOut,
    ReviewListItem,
    ReviewOut,
    FindingOut,
    CategoryScoreOut,
)
from app.services.review_service import (
    create_code_review,
    get_review,
    list_reviews,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("/code", response_model=ReviewOut)
async def review_code_snippet(
    request: CodeReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Review a pasted code snippet."""
    review = await create_code_review(
        db=db,
        redis=redis,
        request=request,
        user_id=str(current_user.id),
        review_type=ReviewType.CODE_SNIPPET,
    )
    await db.refresh(review)
    return _review_to_out(review)


@router.post("/file", response_model=ReviewOut)
async def review_file_upload(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    detail_level: str = Form("detailed"),
    ai_provider: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Review an uploaded code file (max 1MB)."""
    MAX_SIZE = 1_000_000  # 1MB
    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        from fastapi import HTTPException
        raise HTTPException(status_code=413, detail="File too large (max 1MB)")

    code_content = content.decode("utf-8", errors="replace")

    request = CodeReviewRequest(
        content=code_content,
        language=language or _detect_language(file.filename or ""),
        filename=file.filename,
        detail_level=detail_level,
        ai_provider=ai_provider,
    )
    review = await create_code_review(
        db=db,
        redis=redis,
        request=request,
        user_id=str(current_user.id),
        review_type=ReviewType.FILE_UPLOAD,
    )
    await db.refresh(review)
    return _review_to_out(review)


@router.get("", response_model=ReviewListOut)
async def list_user_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    review_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated review history for the current user."""
    reviews, total = await list_reviews(
        db=db,
        user_id=str(current_user.id),
        page=page,
        page_size=page_size,
        review_type=review_type,
    )
    return ReviewListOut(
        items=[_review_to_list_item(r) for r in reviews],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{review_id}", response_model=ReviewOut)
async def get_review_detail(
    review_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full review detail including all findings."""
    review = await get_review(db, review_id, str(current_user.id))
    return _review_to_out(review)


# ── Serialisation helpers ──────────────────────────────────────────────────────

def _review_to_out(review) -> dict:
    from app.models.review import ReviewResult, SecurityFinding, PerformanceFinding, CodeSmell, TechnicalDebt

    def finding_out(f) -> dict:
        return {
            "id": str(f.id),
            "severity": f.severity,
            "title": f.title if hasattr(f, "title") else getattr(f, "smell_type", ""),
            "description": f.description,
            "file_path": f.file_path,
            "line_number": getattr(f, "line_number", getattr(f, "line_start", None)),
            "code_snippet": getattr(f, "code_snippet", None),
            "recommendation": getattr(f, "recommendation", getattr(f, "refactoring_suggestion", None)),
            "extra": {},
        }

    return {
        "id": str(review.id),
        "review_type": review.review_type,
        "status": review.status,
        "title": review.title,
        "language": review.language,
        "overall_score": review.overall_score,
        "risk_score": review.risk_score,
        "ai_summary": review.ai_summary,
        "ai_provider": review.ai_provider,
        "ai_model": review.ai_model,
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "category_scores": [
            {
                "category": r.category,
                "score": r.score,
                "summary": r.summary or "",
                "suggestions": r.suggestions or [],
            }
            for r in (review.results or [])
        ],
        "security_findings": [finding_out(f) for f in (review.security_findings or [])],
        "performance_findings": [finding_out(f) for f in (review.performance_findings or [])],
        "code_smells": [finding_out(f) for f in (review.code_smells or [])],
        "technical_debt": [finding_out(f) for f in (review.technical_debt_items or [])],
    }


def _review_to_list_item(review) -> dict:
    return {
        "id": str(review.id),
        "review_type": review.review_type,
        "status": review.status,
        "title": review.title,
        "language": review.language,
        "overall_score": review.overall_score,
        "risk_score": review.risk_score,
        "ai_provider": review.ai_provider,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


def _detect_language(filename: str) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
        ".go": "go", ".rs": "rust", ".cs": "csharp", ".rb": "ruby",
        ".php": "php", ".cpp": "cpp", ".c": "c", ".kt": "kotlin",
    }
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    return ext_map.get(suffix, "auto")
