"""Repo chat router — sessions under a repository, messages under a session."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.rate_limit import AI_LIMIT, limiter
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.chat import ChatMessageCreate, ChatMessageOut, ChatSessionCreate, ChatSessionOut
from app.services import chat_service

router = APIRouter(tags=["chat"])


def get_session_factory():
    """The streaming body needs its own DB session; tests override this to share theirs."""
    return AsyncSessionLocal


@router.post("/repositories/{repo_id}/chat/sessions", response_model=ChatSessionOut, status_code=201)
async def create_chat_session(
    repo_id: uuid.UUID,
    payload: ChatSessionCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.create_session(db, current_user, repo_id, payload.title if payload else None)


@router.get("/repositories/{repo_id}/chat/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.list_sessions(db, current_user, repo_id)


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_chat_messages(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.list_messages(db, current_user, session_id)


@router.post("/chat/sessions/{session_id}/messages")
@limiter.limit(AI_LIMIT)
async def send_chat_message(
    request: Request,
    session_id: uuid.UUID,
    payload: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_factory=Depends(get_session_factory),
):
    """Answer as Server-Sent Events: `token`* → `citations` → `done`, or `error`."""
    # Check ownership and index state BEFORE streaming, so these return a normal 404/409.
    _, repo = await chat_service.get_owned_session(db, current_user.id, session_id)
    chat_service.ensure_indexed(repo)
    return StreamingResponse(
        chat_service.stream_answer(session_factory, current_user.id, session_id, payload.content.strip()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # don't let proxies buffer tokens
            # GZipMiddleware (Starlette 0.41) buffers streamed bodies inside its compressor and skips
            # responses that already declare an encoding — this keeps tokens flowing one by one.
            "Content-Encoding": "identity",
        },
    )


@router.delete("/chat/sessions/{session_id}", status_code=204)
async def delete_chat_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await chat_service.delete_session(db, current_user, session_id)
