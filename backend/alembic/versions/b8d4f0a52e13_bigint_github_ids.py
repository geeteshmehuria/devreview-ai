"""widen GitHub ids to BIGINT

GitHub pull request ids are already above the int32 maximum, and repository
ids are heading there, so inserts failed with "value out of int32 range".

Revision ID: b8d4f0a52e13
Revises: a7c3e9d41f02
Create Date: 2026-11-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b8d4f0a52e13'
down_revision: Union[str, None] = 'a7c3e9d41f02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('pull_requests', 'github_pr_id', existing_type=sa.Integer(), type_=sa.BigInteger())
    op.alter_column('repositories', 'github_repo_id', existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    op.alter_column('repositories', 'github_repo_id', existing_type=sa.BigInteger(), type_=sa.Integer())
    op.alter_column('pull_requests', 'github_pr_id', existing_type=sa.BigInteger(), type_=sa.Integer())
