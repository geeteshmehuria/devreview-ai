"""
ARQ worker.

Run on its own (WORKER_MODE=external):   arq app.jobs.worker.WorkerSettings
Run inside the API (WORKER_MODE=embedded): started/stopped by the FastAPI lifespan via
start_embedded_worker() / stop_embedded_worker(). Same queue and functions either way, so moving
from one to the other is a config change, not a code change.
"""

import asyncio
from typing import Any

import redis.asyncio as aioredis
import structlog
from arq import Worker
from arq.worker import func
from sqlalchemy import or_, select, update

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis_pool
from app.jobs.queue import (
    ANALYSIS_JOB,
    INDEX_JOB,
    QUEUE_NAME,
    analysis_job_id,
    index_job_id,
    job_is_active,
    redis_settings,
)
from app.jobs.tasks import analyze_repository_job, index_repository_job
from app.models.repository import IndexStatus, Repository, RepositoryStatus

logger = structlog.get_logger()
settings = get_settings()

INTERRUPTED_INDEX_ERROR = "Indexing was interrupted and could not be resumed. Please try again."


async def reconcile_stale_jobs(queue, session_factory=AsyncSessionLocal) -> int:
    """Mark repos failed when they say "indexing"/"analyzing" but no job exists for them any more.

    With a persistent Redis an interrupted job is simply run again, so those repos are left
    alone. Without one (or after JOB_MAX_TRIES), the job is gone and the UI would otherwise show
    the spinner forever. Returns how many repos were reset.
    """
    reset = 0
    async with session_factory() as session:
        repos = (
            await session.execute(
                select(Repository.id, Repository.index_status, Repository.status).where(
                    or_(Repository.index_status == IndexStatus.INDEXING, Repository.status == RepositoryStatus.ANALYZING)
                )
            )
        ).all()
        for repo_id, index_status, status in repos:
            if index_status == IndexStatus.INDEXING and not await job_is_active(queue, index_job_id(repo_id)):
                await session.execute(
                    update(Repository)
                    .where(Repository.id == repo_id)
                    .values(index_status=IndexStatus.FAILED, index_error=INTERRUPTED_INDEX_ERROR)
                )
                reset += 1
            if status == RepositoryStatus.ANALYZING and not await job_is_active(queue, analysis_job_id(repo_id)):
                await session.execute(
                    update(Repository).where(Repository.id == repo_id).values(status=RepositoryStatus.FAILED)
                )
                reset += 1
        await session.commit()
    if reset:
        logger.info("stale_jobs_reconciled", reset=reset)
    return reset


async def startup(ctx: dict[str, Any]) -> None:
    # ctx["redis"] is ARQ's own (bytes) connection; the app's cache helpers expect decoded strings.
    ctx["app_redis"] = aioredis.Redis(connection_pool=get_redis_pool())
    ctx["session_factory"] = AsyncSessionLocal
    if settings.WORKER_MODE == "external":
        # In embedded mode the API lifespan already ran this before starting the worker.
        try:
            await reconcile_stale_jobs(ctx["redis"])
        except Exception as e:
            logger.warning("stale_jobs_reconcile_failed", error=str(e))
    logger.info("worker_started", mode=settings.WORKER_MODE, max_jobs=settings.WORKER_MAX_JOBS)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["app_redis"].aclose()


class WorkerSettings:
    functions = [
        func(index_repository_job, name=INDEX_JOB, max_tries=settings.JOB_MAX_TRIES),
        func(analyze_repository_job, name=ANALYSIS_JOB, max_tries=settings.JOB_MAX_TRIES),
    ]
    queue_name = QUEUE_NAME
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = settings.WORKER_MAX_JOBS
    poll_delay = settings.WORKER_POLL_DELAY_SECONDS
    # The job enforces JOB_TIMEOUT_SECONDS itself (so it can save a readable error); ARQ's limit is
    # only a backstop for a job that ignores cancellation.
    job_timeout = settings.JOB_TIMEOUT_SECONDS + 60
    keep_result = 0  # nothing reads results; dropping them lets the same job id be queued again
    health_check_interval = 3600  # one Redis write an hour


# ── Embedded mode ──────────────────────────────────────────────────────────────

_worker: Worker | None = None
_runner: asyncio.Task | None = None


def start_embedded_worker() -> None:
    """Run the worker as a background task of the API process."""
    global _worker, _runner
    _worker = Worker(
        functions=WorkerSettings.functions,
        queue_name=WorkerSettings.queue_name,
        redis_settings=WorkerSettings.redis_settings,
        on_startup=WorkerSettings.on_startup,
        on_shutdown=WorkerSettings.on_shutdown,
        max_jobs=WorkerSettings.max_jobs,
        poll_delay=WorkerSettings.poll_delay,
        job_timeout=WorkerSettings.job_timeout,
        keep_result=WorkerSettings.keep_result,
        health_check_interval=WorkerSettings.health_check_interval,
        handle_signals=False,  # uvicorn owns SIGTERM; the lifespan stops us
    )
    _runner = asyncio.create_task(_run(_worker), name="arq-embedded-worker")


RESTART_DELAY_SECONDS = 30


async def _run(worker: Worker) -> None:
    """Keep the worker alive: if Redis is down at boot or drops later, the API keeps serving and
    the worker reconnects instead of silently leaving jobs queued until the next deploy."""
    while True:
        try:
            await worker.async_run()
            return
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("embedded_worker_crashed", error=str(e), retry_in=RESTART_DELAY_SECONDS)
            await asyncio.sleep(RESTART_DELAY_SECONDS)


async def stop_embedded_worker() -> None:
    """Cancel running jobs (ARQ re-queues them for the next process) and close the worker."""
    global _worker, _runner
    if _worker is not None:
        try:
            await _worker.close()
        except Exception as e:
            logger.warning("embedded_worker_close_failed", error=str(e))
    if _runner is not None:
        _runner.cancel()
        try:
            await _runner
        except asyncio.CancelledError:
            pass
    _worker, _runner = None, None
