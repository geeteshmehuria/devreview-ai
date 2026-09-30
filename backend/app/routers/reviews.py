"""Review router — code review endpoints."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.rate_limit import AI_LIMIT, limiter
from app.core.redis import get_redis
from app.middleware.auth import get_current_user
from app.models.review import Review, ReviewType
from app.models.user import User
from app.schemas.review import (
    MAX_CODE_CHARS,
    CodeReviewRequest,
    DebtItemOut,
    DetailLevel,
    ProviderName,
    ReviewListOut,
    ReviewOut,
)
from app.services.review_service import create_code_review, get_review, list_reviews, list_technical_debt

router = APIRouter(prefix="/reviews", tags=["reviews"])

MAX_UPLOAD_BYTES = MAX_CODE_CHARS  # same cap as pasted code (100 KB)


@router.post("/code", response_model=ReviewOut)
@limiter.limit(AI_LIMIT)
async def review_code_snippet(
    request: Request,
    payload: CodeReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Review a pasted code snippet."""
    review = await create_code_review(db, redis, payload, str(current_user.id), ReviewType.CODE_SNIPPET)
    return _review_to_out(await get_review(db, review.id, current_user.id))


@router.post("/file", response_model=ReviewOut)
@limiter.limit(AI_LIMIT)
async def review_file_upload(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("auto"),
    detail_level: DetailLevel = Form("detailed"),
    ai_provider: ProviderName | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Review an uploaded code file (max 100 KB)."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 100 KB)")

    if language == "auto":
        language = _detect_language(file.filename or "")
    try:
        payload = CodeReviewRequest(
            content=content.decode("utf-8", errors="replace"),
            language=language,
            filename=file.filename,
            detail_level=detail_level,
            ai_provider=ai_provider,
        )
    except ValidationError:
        raise HTTPException(status_code=422, detail="File must contain at least 10 characters of text")

    review = await create_code_review(db, redis, payload, str(current_user.id), ReviewType.FILE_UPLOAD)
    return _review_to_out(await get_review(db, review.id, current_user.id))


@router.get("", response_model=ReviewListOut)
async def list_user_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    review_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated review history for the current user."""
    reviews, total = await list_reviews(db, current_user.id, page, page_size, review_type)
    return ReviewListOut(
        items=[_review_to_list_item(r) for r in reviews],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/debt", response_model=list[DebtItemOut])
async def list_debt_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Technical-debt items found across all of the current user's reviews."""
    return [
        {
            "id": str(d.id),
            "review_id": str(r.id),
            "review_title": r.title,
            "category": d.category,
            "severity": d.severity,
            "title": d.title,
            "description": d.description,
            "file_path": d.file_path,
            "estimated_hours": d.estimated_hours,
            "recommendation": d.recommendation,
            "created_at": _iso(d.created_at),
        }
        for d, r in await list_technical_debt(db, current_user.id)
    ]


@router.get("/{review_id}", response_model=ReviewOut)
async def get_review_detail(
    review_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full review detail including all findings."""
    return _review_to_out(await get_review(db, review_id, current_user.id))


# ── Serialisation helpers ──────────────────────────────────────────────────────

def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _finding_out(f, *, title=None, line=None, recommendation=None, extra=None) -> dict:
    return {
        "id": str(f.id),
        "severity": f.severity,
        "title": title if title is not None else f.title,
        "description": f.description,
        "file_path": f.file_path,
        "line_number": line,
        "code_snippet": getattr(f, "code_snippet", None),
        "recommendation": recommendation,
        "extra": {k: v for k, v in (extra or {}).items() if v is not None},
    }


def _review_to_out(review: Review) -> dict:
    return {
        **_review_to_list_item(review),
        "ai_summary": review.ai_summary,
        "ai_model": review.ai_model,
        "category_scores": [
            {"category": r.category, "score": r.score, "summary": r.summary or "", "suggestions": r.suggestions or []}
            for r in review.results
        ],
        "security_findings": [
            _finding_out(f, line=f.line_number, recommendation=f.recommendation, extra={"cwe_id": f.cwe_id})
            for f in review.security_findings
        ],
        "performance_findings": [
            _finding_out(f, line=f.line_number, recommendation=f.recommendation, extra={"impact": f.impact})
            for f in review.performance_findings
        ],
        "code_smells": [
            _finding_out(f, title=f.smell_type, line=f.line_start, recommendation=f.refactoring_suggestion)
            for f in review.code_smells
        ],
        "technical_debt": [
            _finding_out(
                f, recommendation=f.recommendation,
                extra={"category": f.category, "estimated_hours": f.estimated_hours},
            )
            for f in review.technical_debt_items
        ],
    }


def _review_to_list_item(review: Review) -> dict:
    return {
        "id": str(review.id),
        "review_type": review.review_type,
        "status": review.status,
        "title": review.title,
        "language": review.language,
        "overall_score": review.overall_score,
        "risk_score": review.risk_score,
        "ai_provider": review.ai_provider,
        "created_at": _iso(review.created_at),
    }


_EXT_LANGUAGES = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
    ".go": "go", ".rs": "rust", ".cs": "csharp", ".rb": "ruby",
    ".php": "php", ".cpp": "cpp", ".c": "c", ".kt": "kotlin",
    ".swift": "swift", ".scala": "scala", ".vue": "vue", ".svelte": "svelte",
}


def _detect_language(filename: str) -> str:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_LANGUAGES.get(suffix, "auto")
