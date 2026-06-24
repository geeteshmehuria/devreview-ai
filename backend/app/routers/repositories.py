"""Repository router."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
import uuid

from app.core.database import get_db
from app.core.redis import get_redis
from app.middleware.auth import get_current_user
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryOut, RepositoryDetailOut
from app.services.repository_service import import_repository, analyze_repository
from app.schemas.review import RepoAnalysisRequest

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryOut)
async def add_repository(
    payload: RepoAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Import a GitHub repository and trigger background analysis."""
    repo = await import_repository(
        db=db,
        user_id=str(current_user.id),
        repo_url=payload.repo_url,
        github_token=current_user.github_access_token or "",
    )

    # Fire analysis in background so HTTP response returns immediately
    background_tasks.add_task(
        _run_analysis_background,
        db, redis,
        str(repo.id), str(current_user.id),
        payload.force_refresh,
    )

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
    repos = result.scalars().all()
    return [_repo_to_out(r) for r in repos]


@router.get("/{repo_id}", response_model=RepositoryDetailOut)
async def get_repository(
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    from app.core.exceptions import NotFoundError

    result = await db.execute(
        select(Repository)
        .options(selectinload(Repository.health_snapshots))
        .where(
            Repository.id == uuid.UUID(repo_id),
            Repository.owner_id == current_user.id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")
    return _repo_detail_to_out(repo)


@router.post("/{repo_id}/analyze", response_model=RepositoryOut)
async def trigger_analysis(
    repo_id: str,
    background_tasks: BackgroundTasks,
    force_refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Re-trigger analysis on demand."""
    from app.core.exceptions import NotFoundError
    result = await db.execute(
        select(Repository).where(
            Repository.id == uuid.UUID(repo_id),
            Repository.owner_id == current_user.id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")

    background_tasks.add_task(
        _run_analysis_background,
        db, redis,
        repo_id, str(current_user.id), force_refresh,
    )
    return _repo_to_out(repo)


@router.delete("/{repo_id}", status_code=204)
async def delete_repository(
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.exceptions import NotFoundError
    result = await db.execute(
        select(Repository).where(
            Repository.id == uuid.UUID(repo_id),
            Repository.owner_id == current_user.id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")
    await db.delete(repo)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _run_analysis_background(db, redis, repo_id, user_id, force_refresh):
    """Background task wrapper — needs its own DB session."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        try:
            await analyze_repository(session, redis, repo_id, user_id, force_refresh)
            await session.commit()
        except Exception as e:
            import structlog
            structlog.get_logger().error("bg_analysis_failed", error=str(e))
            await session.rollback()


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
        for h in (repo.health_snapshots or [])
    ]
    return out
