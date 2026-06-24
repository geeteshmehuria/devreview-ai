"""
Abstract base class for all AI providers.
Business logic never imports a concrete provider — only this interface.

Design decisions:
- ReviewRequest is provider-agnostic structured input
- ReviewResponse normalises output regardless of which model generated it
- Subclasses handle prompt construction and API calls
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewRequest:
    """Input to the AI review pipeline."""

    review_type: str          # "repository" | "pull_request" | "code_snippet" | "file_upload"
    content: str              # Code, diff, or repository structure
    language: str = "auto"   # Detected or declared language
    context: dict = field(default_factory=dict)  # Extra metadata (filename, PR title, etc.)
    detail_level: str = "detailed"  # "brief" | "detailed" | "comprehensive"


@dataclass
class FindingItem:
    severity: str
    title: str
    description: str
    file_path: str | None = None
    line_number: int | None = None
    code_snippet: str | None = None
    recommendation: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class CategoryScore:
    category: str        # "security" | "performance" | "readability" | ...
    score: float         # 0-100
    summary: str
    suggestions: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class ReviewResponse:
    """Normalised AI review output — provider-agnostic."""

    overall_score: float
    risk_score: float
    ai_summary: str
    language: str

    # Category breakdown
    category_scores: list[CategoryScore] = field(default_factory=list)

    # Findings
    security_findings: list[FindingItem] = field(default_factory=list)
    performance_findings: list[FindingItem] = field(default_factory=list)
    code_smells: list[FindingItem] = field(default_factory=list)
    technical_debt: list[FindingItem] = field(default_factory=list)

    # Token usage
    prompt_tokens: int = 0
    completion_tokens: int = 0

    # Provider metadata
    provider: str = ""
    model: str = ""
    raw_response: Any = None


class AIProvider(ABC):
    """
    Abstract AI provider.
    Each implementation must translate a ReviewRequest into a ReviewResponse.
    """

    provider_name: str = "base"
    model_name: str = "unknown"

    @abstractmethod
    async def review(self, request: ReviewRequest) -> ReviewResponse:
        """Run a code review and return a normalised response."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} model={self.model_name}>"
