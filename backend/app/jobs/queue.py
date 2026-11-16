"""
Enqueue side of the job queue (used by the API).

Each job id is "<kind>:<repo_id>", and ARQ refuses a second job with an id that is still queued
or running — so double-clicking "Index" or "Re-analyse" never starts two runs of the same repo.
Results are not kept (keep_result=0 in the worker), so the same id can be queued again once the
run has finished.
"""

import uuid

import structlog
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus
from fastapi import status
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.exceptions import AppException

logger = structlog.get_logger()
settings = get_settings()

QUEUE_NAME = "devreview:jobs"
INDEX_JOB = "index_repository"
ANALYSIS_JOB = "analyze_repository"

_ACTIVE = {JobStatus.queued, JobStatus.deferred, JobStatus.in_progress}

_pool: ArqRedis | None = None


class JobQueueUnavailable(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "Background jobs are unavailable right now. Please try again in a minute."


def redis_settings() -> RedisSettings:
    rs = RedisSettings.from_dsn(settings.REDIS_URL)
    rs.conn_timeout = 3
    rs.conn_retries = 2  # fail fast in a request instead of hanging the user for 5+ seconds
    return rs


def index_job_id(repo_id: uuid.UUID | str) -> str:
    return f"index:{repo_id}"


def analysis_job_id(repo_id: uuid.UUID | str) -> str:
    return f"analysis:{repo_id}"


async def get_queue() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings(), default_queue_name=QUEUE_NAME)
    return _pool


async def close_queue() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def _enqueue(function: str, job_id: str, *args) -> bool:
    """True if queued, False if the same job is already queued or running."""
    try:
        queue = await get_queue()
        job = await queue.enqueue_job(function, *args, _job_id=job_id, _queue_name=QUEUE_NAME)
    except (RedisError, OSError) as e:
        logger.error("job_enqueue_failed", function=function, job_id=job_id, error=str(e))
        raise JobQueueUnavailable() from e
    logger.info("job_enqueued" if job else "job_already_active", function=function, job_id=job_id)
    return job is not None


async def enqueue_indexing(repo_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _enqueue(INDEX_JOB, index_job_id(repo_id), str(repo_id), str(user_id))


async def enqueue_analysis(repo_id: uuid.UUID, user_id: uuid.UUID, force_refresh: bool) -> bool:
    return await _enqueue(ANALYSIS_JOB, analysis_job_id(repo_id), str(repo_id), str(user_id), force_refresh)


async def job_is_active(queue: ArqRedis, job_id: str) -> bool:
    return await Job(job_id, queue, _queue_name=QUEUE_NAME).status() in _ACTIVE
