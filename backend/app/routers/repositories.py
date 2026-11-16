"""Repository router."""

import uuid

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.rate_limit import AI_LIMIT, limiter
from app.middleware.auth import get_current_user
from app.models.repository import IndexStatus, Repository, RepositoryStatus
from app.models.user import User
from app.jobs.queue import JobQueueUnavailable, enqueue_analysis, enqueue_indexing
from app.rag.indexer import can_start_indexing
from app.schemas.repository import GitHubRepoOut, IndexStatusOut, RepositoryDetailOut, RepositoryOut
from app.schemas.review import RepoAnalysisRequest
from app.services.repository_service import import_repository, list_user_repos

router = APIRouter(prefix="/repositories", tags=["repositories"])
logger = structlog.get_logger()


@router.post("", response_model=RepositoryOut)
@limiter.limit(AI_LIMIT)
async def add_repository(
    request: Request,
    payload: RepoAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a GitHub repository and queue its analysis (the worker runs it)."""
    repo = await import_repository(db, current_user, payload.repo_url)
    await db.commit()  # the job uses its own session and must see this row
    await _queue_analysis(db, repo, current_user, payload.force_refresh)
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


# Declared before /{repo_id} so "github" isn't parsed as a repository id.
@router.get("/github", response_model=list[GitHubRepoOut])
async def list_github_repositories(current_user: User = Depends(get_current_user)):
    """List the current user's GitHub repositories so they can pick one to import."""
    return await list_user_repos(current_user)


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
    force_refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-trigger analysis on demand."""
    repo = await _get_owned_repo(db, repo_id, current_user)
    await _queue_analysis(db, repo, current_user, force_refresh)
    return _repo_to_out(repo)


@router.post("/{repo_id}/index", response_model=IndexStatusOut)
@limiter.limit(AI_LIMIT)
async def start_indexing(
    request: Request,
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a RAG index build for chat. Returns the current state if a run is already in progress.

    The result arrives as an `index_status` event on GET /events (see app/jobs).
    """
    repo = await _get_owned_repo(db, repo_id, current_user)
    if can_start_indexing(repo):
        previous = (repo.index_status, repo.index_error)
        repo.index_status = IndexStatus.INDEXING
        repo.index_error = None
        await db.commit()  # visible to the UI and to the job's own session
        try:
            await enqueue_indexing(repo.id, current_user.id)
        except JobQueueUnavailable:
            repo.index_status, repo.index_error = previous  # don't leave a spinner with no job behind it
            await db.commit()
            raise
    return repo


@router.get("/{repo_id}/index-status", response_model=IndexStatusOut)
async def get_index_status(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_repo(db, repo_id, current_user)


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


async def _queue_analysis(db: AsyncSession, repo: Repository, user: User, force_refresh: bool) -> None:
    """Mark the repo "analyzing" and queue the job; the result arrives as a `repo_status` event."""
    previous = repo.status
    repo.status = RepositoryStatus.ANALYZING
    await db.commit()  # the UI shows progress straight away, even while the job waits in the queue
    try:
        await enqueue_analysis(repo.id, user.id, force_refresh)
    except JobQueueUnavailable:
        repo.status = previous
        await db.commit()
        raise


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
