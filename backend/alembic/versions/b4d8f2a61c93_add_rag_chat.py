"""add RAG chat: pgvector, code_chunks, chat_sessions, chat_messages, repository index state

Revision ID: b4d8f2a61c93
Revises: a7c3e9d41f02
Create Date: 2026-11-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'b4d8f2a61c93'
down_revision: Union[str, None] = 'a7c3e9d41f02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768  # must match app.models.code_chunk.EMBEDDING_DIM


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column('repositories', sa.Column('index_status', sa.String(length=20), server_default='not_indexed', nullable=False))
    op.add_column('repositories', sa.Column('indexed_commit_sha', sa.String(length=40), nullable=True))
    op.add_column('repositories', sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('repositories', sa.Column('index_error', sa.Text(), nullable=True))
    op.add_column('repositories', sa.Column('chunk_count', sa.Integer(), server_default='0', nullable=False))

    op.create_table('code_chunks',
    sa.Column('repository_id', sa.UUID(), nullable=False),
    sa.Column('file_path', sa.Text(), nullable=False),
    sa.Column('start_line', sa.Integer(), nullable=False),
    sa.Column('end_line', sa.Integer(), nullable=False),
    sa.Column('symbol_name', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=50), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('commit_sha', sa.String(length=40), nullable=False),
    sa.Column('embedding', Vector(EMBEDDING_DIM), nullable=False),
    sa.Column('search_text', postgresql.TSVECTOR(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_code_chunks_id'), 'code_chunks', ['id'], unique=False)
    op.create_index(op.f('ix_code_chunks_repository_id'), 'code_chunks', ['repository_id'], unique=False)
    op.create_index(
        'ix_code_chunks_embedding_hnsw', 'code_chunks', ['embedding'], unique=False,
        postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.create_index('ix_code_chunks_search_text_gin', 'code_chunks', ['search_text'], unique=False, postgresql_using='gin')

    op.create_table('chat_sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('repository_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_sessions_id'), 'chat_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_chat_sessions_repository_id'), 'chat_sessions', ['repository_id'], unique=False)

    op.create_table('chat_messages',
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('provider', sa.String(length=50), nullable=True),
    sa.Column('model', sa.String(length=100), nullable=True),
    sa.Column('prompt_tokens', sa.Integer(), nullable=True),
    sa.Column('completion_tokens', sa.Integer(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
    op.drop_table('chat_messages')

    op.drop_index(op.f('ix_chat_sessions_repository_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_user_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')

    op.drop_index('ix_code_chunks_search_text_gin', table_name='code_chunks')
    op.drop_index('ix_code_chunks_embedding_hnsw', table_name='code_chunks')
    op.drop_index(op.f('ix_code_chunks_repository_id'), table_name='code_chunks')
    op.drop_index(op.f('ix_code_chunks_id'), table_name='code_chunks')
    op.drop_table('code_chunks')

    op.drop_column('repositories', 'chunk_count')
    op.drop_column('repositories', 'index_error')
    op.drop_column('repositories', 'indexed_at')
    op.drop_column('repositories', 'indexed_commit_sha')
    op.drop_column('repositories', 'index_status')

    # Nothing else in the schema uses pgvector, so a full downgrade leaves the DB as it was.
    op.execute("DROP EXTENSION IF EXISTS vector")
