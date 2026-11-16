"""
Repo chat: sessions, messages and the RAG answer pipeline.

stream_answer():  history → rewrite follow-up into a standalone question → retrieve (hybrid +
findings) → build prompt → stream tokens (provider fallback only before the first token) →
save both messages with the citations the answer actually used.
"""

import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import run_chat, run_chat_stream
from app.core.exceptions import AppException, NotFoundError, RepositoryNotIndexedError
from app.models.chat import ChatMessage, ChatRole, ChatSession
from app.models.repository import Repository
from app.models.user import User
from app.rag.embedder import GeminiEmbedder
from app.rag.prompt import (
    REWRITE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_context,
    build_user_message,
    cited_numbers,
    history_messages,
)
from app.rag.retriever import retrieve

logger = structlog.get_logger()

DEFAULT_TITLE = "New chat"
HISTORY_MESSAGES = 6  # last 3 question/answer pairs
MAX_REWRITE_CHARS = 500

_embedder: GeminiEmbedder | None = None


def _get_embedder() -> GeminiEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = GeminiEmbedder()  # reuse one client (connection pool) across requests
    return _embedder


# ── Sessions ──────────────────────────────────────────────────────────────────

async def _owned_repo(db: AsyncSession, repo_id: uuid.UUID, user: User) -> Repository:
    repo = (
        await db.execute(select(Repository).where(Repository.id == repo_id, Repository.owner_id == user.id))
    ).scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")
    return repo


async def get_owned_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[ChatSession, Repository]:
    """The session must belong to the user AND sit on a repository the user owns."""
    row = (
        await db.execute(
            select(ChatSession, Repository)
            .join(Repository, Repository.id == ChatSession.repository_id)
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id, Repository.owner_id == user_id)
        )
    ).one_or_none()
    if not row:
        raise NotFoundError("Chat session not found")
    return row[0], row[1]


def ensure_indexed(repo: Repository) -> None:
    # indexed_commit_sha is only set by a successful run, so a re-index in progress (or a failed
    # one, which rolls back) still leaves the previous index usable.
    if not repo.indexed_commit_sha:
        raise RepositoryNotIndexedError()


async def create_session(db: AsyncSession, user: User, repo_id: uuid.UUID, title: str | None) -> ChatSession:
    repo = await _owned_repo(db, repo_id, user)
    session = ChatSession(user_id=user.id, repository_id=repo.id, title=(title or "").strip() or DEFAULT_TITLE)
    db.add(session)
    await db.flush()
    await db.refresh(session)  # load server-side timestamps for the response
    return session


async def list_sessions(db: AsyncSession, user: User, repo_id: uuid.UUID) -> list[ChatSession]:
    await _owned_repo(db, repo_id, user)
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.repository_id == repo_id, ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def list_messages(db: AsyncSession, user: User, session_id: uuid.UUID) -> list[ChatMessage]:
    await get_owned_session(db, user.id, session_id)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def delete_session(db: AsyncSession, user: User, session_id: uuid.UUID) -> None:
    session, _ = await get_owned_session(db, user.id, session_id)
    await db.delete(session)  # messages go with it (ON DELETE CASCADE)


# ── Answering ─────────────────────────────────────────────────────────────────

def sse(event: str, data: dict) -> str:
    """One Server-Sent Event. JSON data keeps newlines in tokens from breaking the framing."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def rewrite_question(history: list[tuple[str, str]], question: str) -> str:
    """
    "What about the second one?" can't be searched. Ask the LLM to turn a follow-up into a
    standalone question for retrieval. If rewriting fails, search with the original question.
    """
    try:
        rewritten = (await run_chat(REWRITE_SYSTEM_PROMPT, [*history_messages(history), {"role": "user", "content": question}])).strip()
    except AppException as e:
        logger.warning("chat_rewrite_failed", error=e.detail)
        return question
    return rewritten if 0 < len(rewritten) <= MAX_REWRITE_CHARS else question


async def stream_answer(
    session_factory: Callable,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    question: str,
    embedder: GeminiEmbedder | None = None,
) -> AsyncIterator[str]:
    """
    SSE events: token* → citations → done, or error. Opens its own DB session: FastAPI closes the
    request's session before a StreamingResponse body runs. Messages are saved only when the answer
    completes; if the client disconnects mid-answer, nothing is saved.
    """
    async with session_factory() as db:
        try:
            chat, repo = await get_owned_session(db, user_id, session_id)
            ensure_indexed(repo)
            asked_at = datetime.now(UTC)

            recent = (
                await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == chat.id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(HISTORY_MESSAGES)
                )
            ).scalars().all()
            history = [(m.role, m.content) for m in reversed(recent)]

            search_query = await rewrite_question(history, question) if history else question
            result = await retrieve(db, repo.id, user_id, search_query, embedder or _get_embedder())
            context, citations = build_context(result, repo.url, repo.indexed_commit_sha)
            messages = [
                *history_messages(history),
                {"role": "user", "content": build_user_message(question, context, result.low_confidence)},
            ]

            parts: list[str] = []
            provider = model = None
            prompt_tokens = completion_tokens = None
            async for delta in run_chat_stream(SYSTEM_PROMPT, messages):
                provider, model = delta.provider or provider, delta.model or model
                if delta.text:
                    parts.append(delta.text)
                    yield sse("token", {"text": delta.text})
                if delta.prompt_tokens is not None:
                    prompt_tokens, completion_tokens = delta.prompt_tokens, delta.completion_tokens
            answer = "".join(parts)

            used = [asdict(c) for c in citations if c.n in cited_numbers(answer)]
            yield sse("citations", {"citations": used, "low_confidence": result.low_confidence})

            # Explicit timestamps: a server-side now() is the same for both rows in one transaction.
            db.add(ChatMessage(session_id=chat.id, role=ChatRole.USER, content=question, created_at=asked_at))
            assistant = ChatMessage(
                session_id=chat.id, role=ChatRole.ASSISTANT, content=answer, citations=used,
                provider=provider, model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                created_at=datetime.now(UTC),
            )
            db.add(assistant)
            if chat.title == DEFAULT_TITLE:
                chat.title = question[:80]
            chat.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info("chat_answered", session_id=str(chat.id), provider=provider, chunks=len(result.chunks),
                        cited=len(used), low_confidence=result.low_confidence)
            yield sse("done", {"message_id": str(assistant.id)})
        except AppException as e:
            await db.rollback()
            yield sse("error", {"message": e.detail})
        except Exception:
            logger.exception("chat_failed", session_id=str(session_id))
            await db.rollback()
            yield sse("error", {"message": "Something went wrong while answering. Please try again."})
