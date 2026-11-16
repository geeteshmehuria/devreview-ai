"""
Job functions run by the ARQ worker.

Each job owns its DB session, saves its outcome (success or a readable failure) to Postgres, and
then publishes one event so open browsers update without polling.

Retries: ARQ re-runs a job only when it is cut off (worker shutdown / deploy), up to
JOB_MAX_TRIES. Normal errors are saved as "failed" and not retried — the user retries from the
UI, which keeps a broken repo from burning AI quota in a loop. Both jobs are safe to re-run:
indexing replaces the old chunks in one transaction, and analysis overwrites its snapshot.
"""

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.jobs.events import INDEX_STATUS, REPO_STATUS, publish_event
from app.models.repository import IndexStatus, Repository, RepositoryStatus
from app.rag.indexer import index_repository
from app.schemas.repository import IndexStatusOut
from app.services.repository_service import analyze_repository

logger = structlog.get_logger()
settings = get_settings()

GENERIC_INDEX_ERROR = "Indexing failed unexpectedly. Please try again."
TIMEOUT_INDEX_ERROR = "Indexing took too long and was stopped. Please try again."


def _public_message(e: Exception, default: str) -> str:
    """Only our own exception messages reach the UI; anything else could leak internals."""
    return e.detail if isinstance(e, AppException) else default


async def index_repository_job(ctx: dict[str, Any], repo_id: str, user_id: str) -> None:
    rid, uid = uuid.UUID(repo_id), uuid.UUID(user_id)
    logger.info("job_index_start", repo_id=repo_id, attempt=ctx.get("job_try", 1))
    async with ctx["session_factory"]() as session:
        try:
            async with asyncio.timeout(settings.JOB_TIMEOUT_SECONDS):
                await index_repository(session, rid, uid)
            await session.commit()
        except Exception as e:  # CancelledError is not an Exception: a cut-off run is retried by ARQ
            await session.rollback()
            timed_out = isinstance(e, TimeoutError)
            logger.error("job_index_failed", repo_id=repo_id, error=str(e), timed_out=timed_out)
            message = TIMEOUT_INDEX_ERROR if timed_out else _public_message(e, GENERIC_INDEX_ERROR)
            await session.execute(
                update(Repository)
                .where(Repository.id == rid)
                .values(index_status=IndexStatus.FAILED, index_error=message[:500])
            )
            await session.commit()

        repo = await session.get(Repository, rid, populate_existing=True)
        if repo is not None:
            payload = IndexStatusOut.model_validate(repo).model_dump(mode="json")
            await publish_event(ctx["app_redis"], uid, {"type": INDEX_STATUS, "repo_id": repo_id, **payload})


async def analyze_repository_job(ctx: dict[str, Any], repo_id: str, user_id: str, force_refresh: bool) -> None:
    rid, uid = uuid.UUID(repo_id), uuid.UUID(user_id)
    logger.info("job_analysis_start", repo_id=repo_id, attempt=ctx.get("job_try", 1))
    async with ctx["session_factory"]() as session:
        try:
            async with asyncio.timeout(settings.JOB_TIMEOUT_SECONDS):
                repo = await analyze_repository(session, ctx["app_redis"], rid, uid, force_refresh)
            # A cache hit returns early without touching the status the router set to "analyzing";
            # a cached analysis means the repo was analysed before.
            if repo.status == RepositoryStatus.ANALYZING:
                repo.status = RepositoryStatus.ANALYZED
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("job_analysis_failed", repo_id=repo_id, error=str(e))
            # Persist the failure so the UI stops showing "analyzing" forever.
            await session.execute(
                update(Repository).where(Repository.id == rid).values(status=RepositoryStatus.FAILED)
            )
            await session.commit()

        status = (await session.execute(select(Repository.status).where(Repository.id == rid))).scalar_one_or_none()
        if status is not None:
            await publish_event(
                ctx["app_redis"], uid, {"type": REPO_STATUS, "repo_id": repo_id, "status": str(status)}
            )
