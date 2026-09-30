"""Repository router."""

import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal, get_db
from app.core.exceptions import NotFoundError
from app.core.rate_limit import AI_LIMIT, limiter
from app.core.redis import get_redis_pool
from app.middleware.auth import get_current_user
from app.models.repository import Repository, RepositoryStatus
from app.models.user import User
from app.schemas.repository import RepositoryDetailOut, RepositoryOut
from app.schemas.review import RepoAnalysisRequest
from app.services.repository_service import analyze_repository, import_repository

router = APIRouter(prefix="/repositories", tags=["repositories"])
logger = structlog.get_logger()


@router.post("", response_model=RepositoryOut)
@limiter.limit(AI_LIMIT)
async def add_repository(
    request: Request,
    payload: RepoAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a GitHub repository and trigger background analysis."""
    repo = await import_repository(db, current_user, payload.repo_url)
    await db.commit()  # the background task uses its own session and must see this row

    # Fire analysis in background so HTTP response returns immediately
    background_tasks.add_task(_run_analysis_background, repo.id, current_user.id, payload.force_refresh)
    return _repo_to_out(repo)


@router.get("", response_model=list[RepositoryOut])
async def list_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all repositories imported by the current user."""
    result = await db.execute(
        select(Repository)
        .where(Repository.owner_id == current_user.id)
        .order_by(Repository.created_at.desc())
    )
    return [_repo_to_out(r) for r in result.scalars().all()]


@router.get("/{repo_id}", response_model=RepositoryDetailOut)
async def get_repository(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = await _get_owned_repo(db, repo_id, current_user, selectinload(Repository.health_snapshots))
    return _repo_detail_to_out(repo)


@router.post("/{repo_id}/analyze", response_model=RepositoryOut)
@limiter.limit(AI_LIMIT)
async def trigger_analysis(
    request: Request,
    repo_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    force_refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-trigger analysis on demand."""
    repo = await _get_owned_repo(db, repo_id, current_user)
    background_tasks.add_task(_run_analysis_background, repo.id, current_user.id, force_refresh)
    return _repo_to_out(repo)


@router.delete("/{repo_id}", status_code=204)
async def delete_repository(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(await _get_owned_repo(db, repo_id, current_user))


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_owned_repo(db: AsyncSession, repo_id: uuid.UUID, user: User, *options) -> Repository:
    result = await db.execute(
        select(Repository)
        .options(*options)
        .where(Repository.id == repo_id, Repository.owner_id == user.id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")
    return repo


async def _run_analysis_background(repo_id: uuid.UUID, user_id: uuid.UUID, force_refresh: bool):
    """Background task — owns its DB session and Redis client (the request's are closed by now)."""
    redis = aioredis.Redis(connection_pool=get_redis_pool())
    async with AsyncSessionLocal() as session:
        try:
            await analyze_repository(session, redis, repo_id, user_id, force_refresh)
            await session.commit()
        except Exception as e:
            logger.error("bg_analysis_failed", repo_id=str(repo_id), error=str(e))
            await session.rollback()
            # Persist the failure so the UI stops showing "analyzing" forever.
            await session.execute(
                update(Repository).where(Repository.id == repo_id).values(status=RepositoryStatus.FAILED)
            )
            await session.commit()
        finally:
            await redis.aclose()


def _repo_to_out(repo: Repository) -> dict:
    return {
        "id": str(repo.id),
        "full_name": repo.full_name,
        "name": repo.name,
        "description": repo.description,
        "url": repo.url,
        "language": repo.language,
        "stars": repo.stars,
        "forks": repo.forks,
        "is_private": repo.is_private,
        "status": repo.status,
        "last_analyzed_at": repo.last_analyzed_at,
        "analysis_summary": repo.analysis_summary,
    }


def _repo_detail_to_out(repo: Repository) -> dict:
    out = _repo_to_out(repo)
    out["health_snapshots"] = [
        {
            "id": str(h.id),
            "overall_score": h.overall_score,
            "security_score": h.security_score,
            "performance_score": h.performance_score,
            "maintainability_score": h.maintainability_score,
            "documentation_score": h.documentation_score,
            "complexity_score": h.complexity_score,
            "breakdown": h.breakdown,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in repo.health_snapshots
    ]
    return out
