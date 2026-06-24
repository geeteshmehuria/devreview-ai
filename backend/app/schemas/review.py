"""Review request/response schemas."""

from pydantic import BaseModel, Field


class CodeReviewRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=100_000)
    language: str = "auto"
    filename: str | None = None
    detail_level: str = "detailed"
    ai_provider: str | None = None  # None = use default


class PRReviewRequest(BaseModel):
    pr_url: str = Field(..., pattern=r"https://github\.com/.+/pull/\d+")
    detail_level: str = "detailed"
    ai_provider: str | None = None


class RepoAnalysisRequest(BaseModel):
    repo_url: str = Field(..., pattern=r"https://github\.com/.+/.+")
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

    model_config = {"from_attributes": True}


class CategoryScoreOut(BaseModel):
    category: str
    score: float
    summary: str
    suggestions: list[str]

    model_config = {"from_attributes": True}


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
    created_at: str

    category_scores: list[CategoryScoreOut] = []
    security_findings: list[FindingOut] = []
    performance_findings: list[FindingOut] = []
    code_smells: list[FindingOut] = []
    technical_debt: list[FindingOut] = []

    model_config = {"from_attributes": True}


class ReviewListItem(BaseModel):
    id: str
    review_type: str
    status: str
    title: str | None
    language: str | None
    overall_score: float | None
    risk_score: float | None
    ai_provider: str
    created_at: str

    model_config = {"from_attributes": True}


class ReviewListOut(BaseModel):
    items: list[ReviewListItem]
    total: int
    page: int
    page_size: int
