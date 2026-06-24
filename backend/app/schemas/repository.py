"""Repository schemas."""

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


class RepositoryDetailOut(RepositoryOut):
    health_snapshots: list[HealthSnapshotOut] = []
