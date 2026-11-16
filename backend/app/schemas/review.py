"""Review request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

DetailLevel = Literal["brief", "detailed", "comprehensive"]
ProviderName = Literal["gemini", "openai", "claude"]

MAX_CODE_CHARS = 100_000


class CodeReviewRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=MAX_CODE_CHARS)
    language: str = Field("auto", max_length=50)
    filename: str | None = Field(None, max_length=500)
    detail_level: DetailLevel = "detailed"
    ai_provider: ProviderName | None = None  # None = use default

    @field_validator("content", mode="before")
    @classmethod
    def strip_nul(cls, v):
        """Postgres text columns reject NUL bytes (UTF-16 or binary uploads contain them)."""
        return v.replace("\x00", "") if isinstance(v, str) else v


class PRReviewRequest(BaseModel):
    pr_url: str = Field(..., pattern=r"^https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
    detail_level: DetailLevel = "detailed"
    ai_provider: ProviderName | None = None


class RepoAnalysisRequest(BaseModel):
    repo_url: str = Field(..., pattern=r"^https://github\.com/[\w.-]+/[\w.-]+")
    force_refresh: bool = False


class FindingOut(BaseModel):
    id: str
    severity: str
    title: str
    description: str
    file_path: str | None
    line_number: int | None
    code_snippet: str | None
    recommendation: str | None
    extra: dict


class CategoryScoreOut(BaseModel):
    category: str
    score: float
    summary: str
    suggestions: list[str]


class ReviewOut(BaseModel):
    id: str
    review_type: str
    status: str
    title: str | None
    language: str | None
    overall_score: float | None
    risk_score: float | None
    ai_summary: str | None
    ai_provider: str
    ai_model: str
    error_message: str | None = None
    created_at: str | None

    category_scores: list[CategoryScoreOut] = []
    security_findings: list[FindingOut] = []
    performance_findings: list[FindingOut] = []
    code_smells: list[FindingOut] = []
    technical_debt: list[FindingOut] = []


class ReviewListItem(BaseModel):
    id: str
    review_type: str
    status: str
    title: str | None
    language: str | None
    overall_score: float | None
    risk_score: float | None
    ai_provider: str
    created_at: str | None


class ReviewListOut(BaseModel):
    items: list[ReviewListItem]
    total: int
    page: int
    page_size: int


class DebtItemOut(BaseModel):
    id: str
    review_id: str
    review_title: str | None
    category: str
    severity: str
    title: str
    description: str
    file_path: str | None
    estimated_hours: float | None
    recommendation: str | None
    created_at: str | None
