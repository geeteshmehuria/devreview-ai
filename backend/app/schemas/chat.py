"""Repo chat schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    # [{"n", "kind", "file_path", "start_line", "end_line", "url", "title"}] on assistant messages
    citations: list[dict] | None
    created_at: datetime

    model_config = {"from_attributes": True}
