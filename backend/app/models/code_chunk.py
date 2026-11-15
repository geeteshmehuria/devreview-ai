"""
CodeChunk — one searchable piece of a repository (a function, class or text window), used by RAG chat.

`embedding` (pgvector) and `search_text` (tsvector) only exist on PostgreSQL. On SQLite, used by
the tests, they fall back to JSON / Text so Base.metadata.create_all keeps working (same idea as
JSONType) and a list of floats still round-trips.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDMixin

# Baked into the column type: changing it needs a new migration and a full re-index.
# 768 keeps us under pgvector's 2000-dimension limit for HNSW indexes.
EMBEDDING_DIM = 768

VectorType = JSON().with_variant(Vector(EMBEDDING_DIM), "postgresql")
TSVectorType = Text().with_variant(TSVECTOR(), "postgresql")


class CodeChunk(Base, UUIDMixin):
    __tablename__ = "code_chunks"
    __table_args__ = (
        # Postgres-only index options; SQLite ignores the dialect kwargs and builds plain indexes.
        Index(
            "ix_code_chunks_embedding_hnsw", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_code_chunks_search_text_gin", "search_text", postgresql_using="gin"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)        # already secret-redacted
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VectorType, nullable=False)
    search_text: Mapped[str] = mapped_column(TSVectorType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="code_chunks")  # noqa: F821
