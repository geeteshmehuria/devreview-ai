"""Indexing pipeline and endpoints, with the clone, GitHub and the embedder mocked (SQLite)."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.models import CodeChunk, Repository, User
from app.models.code_chunk import EMBEDDING_DIM
from app.models.repository import IndexStatus
from app.rag import indexer
from app.rag.chunker import Chunk
from app.routers import repositories as repositories_router

SHA_1 = "1" * 40
SHA_2 = "2" * 40


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    async def embed_documents(self, texts):
        self.calls += 1
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]


async def _make_repo(db, login="owner"):
    user = User(github_id=uuid.uuid4().int % 10**9, github_login=login)
    db.add(user)
    await db.flush()
    repo = Repository(
        owner_id=user.id, github_repo_id=uuid.uuid4().int % 10**6, full_name=f"{login}/demo", name="demo",
        url=f"https://github.com/{login}/demo", clone_url=f"https://github.com/{login}/demo.git",
    )
    db.add(repo)
    await db.flush()
    return user, repo


@pytest.fixture
def fake_clone(tmp_path, monkeypatch):
    """A tiny 'repository' on disk instead of a real git clone."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text(
        'GITHUB_TOKEN = "ghp_' + "a" * 36 + '"\n\n\ndef get_github_token(user):\n    return user.token\n'
    )
    (tmp_path / ".env").write_text("SECRET=do-not-index\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("function x() {}\n")
    (tmp_path / "README.md").write_text("# Demo\nHow to run it.\n")

    @asynccontextmanager
    async def cloned(clone_url, token):
        yield tmp_path

    state = {"head": SHA_1}

    async def head_sha(user, repo):
        return state["head"]

    async def git_head(root):
        return state["head"]

    monkeypatch.setattr(indexer, "cloned_repo", cloned)
    monkeypatch.setattr(indexer, "fetch_head_sha", head_sha)
    monkeypatch.setattr(indexer, "_git_head_sha", git_head)
    monkeypatch.setattr(indexer, "get_github_token", lambda user: "token")
    return state


@pytest.mark.asyncio
async def test_index_repository_stores_filtered_redacted_chunks_then_skips_unchanged(db_session, fake_clone):
    user, repo = await _make_repo(db_session)
    embedder = FakeEmbedder()

    await indexer.index_repository(db_session, repo.id, user.id, embedder=embedder)

    rows = (await db_session.execute(select(CodeChunk).where(CodeChunk.repository_id == repo.id))).scalars().all()
    paths = {r.file_path for r in rows}
    assert paths == {"app/auth.py", "README.md"}                 # .env and node_modules skipped
    assert all("ghp_" not in r.content for r in rows)            # secret redacted before storing
    fn = next(r for r in rows if r.symbol_name == "get_github_token")
    assert (fn.start_line, fn.end_line) == (4, 5)
    assert {"github", "token", "auth"} <= set(fn.search_text.split())  # identifiers + path split into words
    assert repo.index_status == IndexStatus.INDEXED
    assert (repo.chunk_count, repo.indexed_commit_sha) == (len(rows), SHA_1)

    # Same HEAD → nothing re-embedded.
    await indexer.index_repository(db_session, repo.id, user.id, embedder=embedder)
    assert embedder.calls == 1

    # New HEAD → chunks replaced, not duplicated.
    fake_clone["head"] = SHA_2
    await indexer.index_repository(db_session, repo.id, user.id, embedder=embedder)
    rows2 = (await db_session.execute(select(CodeChunk).where(CodeChunk.repository_id == repo.id))).scalars().all()
    assert len(rows2) == len(rows) and {r.commit_sha for r in rows2} == {SHA_2}


@pytest.mark.asyncio
async def test_index_repository_rejects_other_users_repo(db_session, fake_clone):
    _, repo = await _make_repo(db_session, "alice")
    bob, _ = await _make_repo(db_session, "bob")
    with pytest.raises(Exception, match="not found"):
        await indexer.index_repository(db_session, repo.id, bob.id, embedder=FakeEmbedder())


def test_search_text_splits_camel_and_snake_case():
    text = indexer.search_text_for(Chunk("lib/api/client.ts", 1, 2, "getGithubToken", "typescript", "refresh_access_token()"))
    for word in ("get", "github", "token", "refresh", "access", "client"):
        assert f" {word}" in text or f"\n{word}" in text


def test_can_start_indexing_stuck_job_rule():
    now = datetime.now(UTC)
    assert indexer.can_start_indexing(Repository(index_status=IndexStatus.NOT_INDEXED, updated_at=now))
    assert indexer.can_start_indexing(Repository(index_status=IndexStatus.FAILED, updated_at=now))
    assert not indexer.can_start_indexing(Repository(index_status=IndexStatus.INDEXING, updated_at=now))
    stale = now - timedelta(minutes=31)
    assert indexer.can_start_indexing(Repository(index_status=IndexStatus.INDEXING, updated_at=stale))
    assert indexer.can_start_indexing(  # naive UTC from SQLite
        Repository(index_status=IndexStatus.INDEXING, updated_at=stale.replace(tzinfo=None))
    )


@pytest.mark.asyncio
async def test_index_endpoints_start_job_once_and_enforce_ownership(client, db_session, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)
    started = []

    async def fake_job(repo_id, user_id):
        started.append(repo_id)

    monkeypatch.setattr(repositories_router, "_run_indexing_background", fake_job)
    user, repo = await _make_repo(db_session, "carol")
    other, _ = await _make_repo(db_session, "dave")
    auth = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    r = await client.post(f"/api/v1/repositories/{repo.id}/index", headers=auth)
    assert r.status_code == 200 and r.json()["index_status"] == "indexing"
    r = await client.post(f"/api/v1/repositories/{repo.id}/index", headers=auth)  # already running
    assert r.status_code == 200 and started == [repo.id]

    r = await client.get(f"/api/v1/repositories/{repo.id}/index-status", headers=auth)
    assert r.json() == {
        "index_status": "indexing", "chunk_count": 0, "indexed_commit_sha": None, "indexed_at": None, "index_error": None,
    }

    other_auth = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
    assert (await client.get(f"/api/v1/repositories/{repo.id}/index-status", headers=other_auth)).status_code == 404
    assert (await client.post(f"/api/v1/repositories/{repo.id}/index", headers=other_auth)).status_code == 404
