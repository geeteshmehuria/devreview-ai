"""Background jobs (ARQ) and live events: tasks, queue errors, stale-job reconcile, SSE stream."""

import asyncio
import json
import uuid

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import GitHubError
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.jobs import events, tasks, worker
from app.jobs.queue import JobQueueUnavailable, index_job_id
from app.main import app
from app.models import Repository, User
from app.models.repository import IndexStatus, RepositoryStatus
from app.routers import events as events_router
from app.routers import repositories as repositories_router

SHA = "a" * 40


class FakeRedis:
    """Records publishes; can be told to fail."""

    def __init__(self, fail=False):
        self.published: list[tuple[str, dict]] = []
        self.fail = fail

    async def publish(self, channel, data):
        if self.fail:
            raise RedisConnectionError("down")
        self.published.append((channel, json.loads(data)))


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(bind=test_engine, expire_on_commit=False)


async def _make_repo(session_factory, **fields):
    async with session_factory() as db:
        login = f"u{uuid.uuid4().hex[:8]}"
        user = User(github_id=uuid.uuid4().int % 10**9, github_login=login)
        db.add(user)
        await db.flush()
        repo = Repository(
            owner_id=user.id, github_repo_id=uuid.uuid4().int % 10**6, full_name=f"{login}/demo", name="demo",
            url=f"https://github.com/{login}/demo", clone_url=f"https://github.com/{login}/demo.git", **fields,
        )
        db.add(repo)
        await db.commit()
        return user, repo


async def _reload(session_factory, repo_id):
    async with session_factory() as db:
        return await db.get(Repository, repo_id)


# ── Events ─────────────────────────────────────────────────────────────────────

def test_format_sse():
    assert events.format_sse("job", {"a": 1}) == 'event: job\ndata: {"a": 1}\n\n'


async def test_publish_event_targets_user_channel_and_never_raises():
    uid = uuid.uuid4()
    ok = FakeRedis()
    await events.publish_event(ok, uid, {"type": "x"})
    assert ok.published == [(f"devreview:events:{uid}", {"type": "x"})]
    await events.publish_event(FakeRedis(fail=True), uid, {"type": "x"})  # swallowed


class FakePubSub:
    def __init__(self, messages):
        self.messages = list(messages)
        self.subscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def get_message(self, timeout):
        if self.messages:
            return self.messages.pop(0)
        await asyncio.sleep(0)
        return None

    async def aclose(self):
        self.closed = True


class FakePubSubRedis:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    def pubsub(self, **_):
        return self._pubsub


async def test_event_stream_ready_then_jobs_then_heartbeat():
    uid = uuid.uuid4()
    ps = FakePubSub([
        {"type": "message", "data": json.dumps({"type": "index_status", "repo_id": "r1"})},
        {"type": "message", "data": "not json"},  # skipped, stream survives
    ])
    stream = events.event_stream(uid, redis=FakePubSubRedis(ps), heartbeat_seconds=0)
    out = [await anext(stream) for _ in range(3)]
    await stream.aclose()

    assert ps.subscribed == [f"devreview:events:{uid}"]
    assert out[0] == "event: ready\ndata: {}\n\n"
    assert json.loads(out[1].split("data: ", 1)[1]) == {"type": "index_status", "repo_id": "r1"}
    assert out[2] == ": ping\n\n"
    assert ps.closed


async def test_event_stream_reports_redis_failure():
    class Broken(FakePubSub):
        async def subscribe(self, channel):
            raise RedisConnectionError("down")

    ps = Broken([])
    out = [chunk async for chunk in events.event_stream(uuid.uuid4(), redis=FakePubSubRedis(ps))]
    assert out == [events.format_sse("error", {"message": "Live updates are unavailable right now."})]
    assert ps.closed


async def test_events_endpoint_requires_auth_and_streams_for_current_user(client, db_session):
    assert (await client.get("/api/v1/events")).status_code == 401

    user = User(github_id=uuid.uuid4().int % 10**9, github_login="streamer")
    db_session.add(user)
    await db_session.flush()
    seen = []

    async def fake_stream(user_id):
        seen.append(user_id)
        yield events.format_sse("ready", {})

    app.dependency_overrides[events_router.get_event_stream] = lambda: fake_stream
    r = await client.get("/api/v1/events", headers={"Authorization": f"Bearer {create_access_token(str(user.id))}"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text == "event: ready\ndata: {}\n\n"
    assert seen == [user.id]


# ── Index job ──────────────────────────────────────────────────────────────────

async def test_index_job_success_saves_and_publishes(session_factory, monkeypatch):
    user, repo = await _make_repo(session_factory, index_status=IndexStatus.INDEXING)

    async def fake_index(db, repo_id, user_id):
        r = await db.get(Repository, repo_id)
        r.index_status, r.indexed_commit_sha, r.chunk_count = IndexStatus.INDEXED, SHA, 12
        return r

    monkeypatch.setattr(tasks, "index_repository", fake_index)
    redis = FakeRedis()
    await tasks.index_repository_job({"session_factory": session_factory, "app_redis": redis}, str(repo.id), str(user.id))

    assert (await _reload(session_factory, repo.id)).index_status == IndexStatus.INDEXED
    (channel, event), = redis.published
    assert channel == f"devreview:events:{user.id}"
    assert event["type"] == "index_status" and event["repo_id"] == str(repo.id)
    assert event["index_status"] == "indexed" and event["chunk_count"] == 12 and event["indexed_commit_sha"] == SHA


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (GitHubError("Could not clone the repository"), "Could not clone the repository"),
        (RuntimeError("secret internals"), tasks.GENERIC_INDEX_ERROR),
    ],
)
async def test_index_job_failure_saves_readable_error(session_factory, monkeypatch, error, message):
    user, repo = await _make_repo(session_factory, index_status=IndexStatus.INDEXING)

    async def failing(*_):
        raise error

    monkeypatch.setattr(tasks, "index_repository", failing)
    redis = FakeRedis()
    await tasks.index_repository_job({"session_factory": session_factory, "app_redis": redis}, str(repo.id), str(user.id))

    saved = await _reload(session_factory, repo.id)
    assert saved.index_status == IndexStatus.FAILED and saved.index_error == message
    assert redis.published[0][1]["index_status"] == "failed"
    assert redis.published[0][1]["index_error"] == message


async def test_index_job_timeout_is_saved_as_failure(session_factory, monkeypatch):
    user, repo = await _make_repo(session_factory, index_status=IndexStatus.INDEXING)

    async def slow(*_):
        await asyncio.sleep(5)

    monkeypatch.setattr(tasks, "index_repository", slow)
    monkeypatch.setattr(tasks.settings, "JOB_TIMEOUT_SECONDS", 0.05)
    await tasks.index_repository_job({"session_factory": session_factory, "app_redis": FakeRedis()}, str(repo.id), str(user.id))

    saved = await _reload(session_factory, repo.id)
    assert saved.index_status == IndexStatus.FAILED and saved.index_error == tasks.TIMEOUT_INDEX_ERROR


async def test_index_job_cancelled_is_left_for_arq_to_retry(session_factory, monkeypatch):
    """A worker shutdown cancels the job; it must stay "indexing" so the re-run continues it."""
    user, repo = await _make_repo(session_factory, index_status=IndexStatus.INDEXING)

    async def cancelled(*_):
        raise asyncio.CancelledError

    monkeypatch.setattr(tasks, "index_repository", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await tasks.index_repository_job({"session_factory": session_factory, "app_redis": FakeRedis()}, str(repo.id), str(user.id))
    assert (await _reload(session_factory, repo.id)).index_status == IndexStatus.INDEXING


# ── Analysis job ───────────────────────────────────────────────────────────────

async def test_analysis_job_cache_hit_ends_analyzed(session_factory, monkeypatch):
    user, repo = await _make_repo(session_factory, status=RepositoryStatus.ANALYZING)

    async def cache_hit(db, redis, repo_id, user_id, force):
        return await db.get(Repository, repo_id)  # returns without touching the status

    monkeypatch.setattr(tasks, "analyze_repository", cache_hit)
    redis = FakeRedis()
    await tasks.analyze_repository_job({"session_factory": session_factory, "app_redis": redis}, str(repo.id), str(user.id), False)

    assert (await _reload(session_factory, repo.id)).status == RepositoryStatus.ANALYZED
    assert redis.published[0][1] == {"type": "repo_status", "repo_id": str(repo.id), "status": "analyzed"}


async def test_analysis_job_failure_marks_failed_and_publishes(session_factory, monkeypatch):
    user, repo = await _make_repo(session_factory, status=RepositoryStatus.ANALYZING)

    async def boom(*_):
        raise RuntimeError("AI down")

    monkeypatch.setattr(tasks, "analyze_repository", boom)
    redis = FakeRedis()
    await tasks.analyze_repository_job({"session_factory": session_factory, "app_redis": redis}, str(repo.id), str(user.id), True)

    assert (await _reload(session_factory, repo.id)).status == RepositoryStatus.FAILED
    assert redis.published[0][1]["status"] == "failed"


# ── Stale-job reconcile ────────────────────────────────────────────────────────

async def test_reconcile_fails_only_repos_whose_job_is_gone(session_factory, monkeypatch):
    _, alive = await _make_repo(session_factory, index_status=IndexStatus.INDEXING)
    _, lost_index = await _make_repo(session_factory, index_status=IndexStatus.INDEXING)
    _, lost_analysis = await _make_repo(session_factory, status=RepositoryStatus.ANALYZING)
    active = {index_job_id(alive.id)}

    async def fake_active(queue, job_id):
        return job_id in active

    monkeypatch.setattr(worker, "job_is_active", fake_active)
    await worker.reconcile_stale_jobs(object(), session_factory)

    assert (await _reload(session_factory, alive.id)).index_status == IndexStatus.INDEXING
    lost = await _reload(session_factory, lost_index.id)
    assert lost.index_status == IndexStatus.FAILED and lost.index_error == worker.INTERRUPTED_INDEX_ERROR
    assert (await _reload(session_factory, lost_analysis.id)).status == RepositoryStatus.FAILED


# ── Endpoints when the queue is down ───────────────────────────────────────────

async def test_index_and_analyze_return_503_and_restore_state_when_queue_is_down(client, db_session, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)

    async def down(*_):
        raise JobQueueUnavailable()

    monkeypatch.setattr(repositories_router, "enqueue_indexing", down)
    monkeypatch.setattr(repositories_router, "enqueue_analysis", down)

    user = User(github_id=uuid.uuid4().int % 10**9, github_login="queueless")
    db_session.add(user)
    await db_session.flush()
    repo = Repository(
        owner_id=user.id, github_repo_id=uuid.uuid4().int % 10**6, full_name="queueless/demo", name="demo",
        url="https://github.com/queueless/demo", clone_url="https://github.com/queueless/demo.git",
        status=RepositoryStatus.ANALYZED,
    )
    db_session.add(repo)
    await db_session.flush()
    auth = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    r = await client.post(f"/api/v1/repositories/{repo.id}/index", headers=auth)
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]
    assert repo.index_status == IndexStatus.NOT_INDEXED

    r = await client.post(f"/api/v1/repositories/{repo.id}/analyze", headers=auth)
    assert r.status_code == 503
    assert repo.status == RepositoryStatus.ANALYZED


async def test_analyze_marks_analyzing_and_queues(client, db_session, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)
    queued = []

    async def fake_enqueue(repo_id, user_id, force):
        queued.append((repo_id, force))
        return True

    monkeypatch.setattr(repositories_router, "enqueue_analysis", fake_enqueue)
    user = User(github_id=uuid.uuid4().int % 10**9, github_login="analyst")
    db_session.add(user)
    await db_session.flush()
    repo = Repository(
        owner_id=user.id, github_repo_id=uuid.uuid4().int % 10**6, full_name="analyst/demo", name="demo",
        url="https://github.com/analyst/demo", clone_url="https://github.com/analyst/demo.git",
    )
    db_session.add(repo)
    await db_session.flush()

    r = await client.post(
        f"/api/v1/repositories/{repo.id}/analyze?force_refresh=true",
        headers={"Authorization": f"Bearer {create_access_token(str(user.id))}"},
    )
    assert r.status_code == 200 and r.json()["status"] == "analyzing"
    assert queued == [(repo.id, True)]
