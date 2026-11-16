"""Repository schemas."""

from datetime import datetime

from pydantic import BaseModel


class RepositoryOut(BaseModel):
    id: str
    full_name: str
    name: str
    description: str | None
    url: str
    language: str | None
    stars: int
    forks: int
    is_private: bool
    status: str
    last_analyzed_at: str | None
    analysis_summary: dict | None

    model_config = {"from_attributes": True}


class GitHubRepoOut(BaseModel):
    """A repo from the user's GitHub account, offered for import."""

    full_name: str
    name: str
    description: str | None
    url: str
    language: str | None
    stars: int
    is_private: bool
    updated_at: str | None


class HealthSnapshotOut(BaseModel):
    id: str
    overall_score: float
    security_score: float
    performance_score: float
    maintainability_score: float
    documentation_score: float
    complexity_score: float
    breakdown: dict | None
    created_at: str

    model_config = {"from_attributes": True}


class IndexStatusOut(BaseModel):
    """RAG index state of a repository (see docs/RAG.md)."""

    index_status: str
    chunk_count: int
    indexed_commit_sha: str | None
    indexed_at: datetime | None
    index_error: str | None

    model_config = {"from_attributes": True}


class RepositoryDetailOut(RepositoryOut):
    health_snapshots: list[HealthSnapshotOut] = []
