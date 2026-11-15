"""The RAG tables must build and round-trip on SQLite, where vector/tsvector fall back to Text."""

import uuid

import pytest
from sqlalchemy import select

from app.models import ChatMessage, ChatSession, CodeChunk, Repository, User
from app.models.repository import IndexStatus


@pytest.mark.asyncio
async def test_rag_models_round_trip_on_sqlite(db_session):
    user = User(github_id=uuid.uuid4().int % 10**9, github_login="rag-user")
    db_session.add(user)
    await db_session.flush()

    repo = Repository(
        owner_id=user.id, github_repo_id=1, full_name="o/r", name="r",
        url="https://github.com/o/r", clone_url="https://github.com/o/r.git",
    )
    db_session.add(repo)
    await db_session.flush()
    assert repo.index_status == IndexStatus.NOT_INDEXED
    assert repo.chunk_count == 0

    db_session.add(CodeChunk(
        repository_id=repo.id, file_path="app/x.py", start_line=1, end_line=3, symbol_name="f",
        language="python", content="def f(): pass", content_hash="0" * 64, commit_sha="a" * 40,
        embedding="[0.1]", search_text="def f pass",  # Text fallback on SQLite
    ))
    session = ChatSession(user_id=user.id, repository_id=repo.id, title="First chat")
    db_session.add(session)
    await db_session.flush()
    db_session.add(ChatMessage(
        session_id=session.id, role="assistant", content="See [1]",
        citations=[{"n": 1, "file_path": "app/x.py", "start_line": 1, "end_line": 3}],
    ))
    await db_session.flush()

    chunk = (await db_session.execute(select(CodeChunk).where(CodeChunk.repository_id == repo.id))).scalar_one()
    msg = (await db_session.execute(select(ChatMessage).where(ChatMessage.session_id == session.id))).scalar_one()
    assert (chunk.start_line, chunk.end_line) == (1, 3)
    assert msg.citations[0]["file_path"] == "app/x.py"
