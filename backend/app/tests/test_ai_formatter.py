"""Tests for the AI response formatter."""

import pytest
from app.ai.response_formatter import format_response, _extract_json
from app.core.exceptions import AIProviderError


VALID_JSON_RESPONSE = """
{
  "overall_score": 78,
  "risk_score": 35,
  "language": "python",
  "ai_summary": "The code is generally well-structured.",
  "category_scores": [
    {
      "category": "security",
      "score": 85,
      "summary": "No critical vulnerabilities found.",
      "suggestions": ["Add input validation"],
      "details": {}
    }
  ],
  "security_findings": [],
  "performance_findings": [
    {
      "severity": "medium",
      "title": "N+1 query",
      "description": "Loop executes separate DB queries",
      "file_path": "app/models.py",
      "line_number": 42,
      "code_snippet": "for user in users:\\n    user.orders.all()",
      "recommendation": "Use select_related() or prefetch_related()",
      "extra": {"impact": "High latency under load"}
    }
  ],
  "code_smells": [],
  "technical_debt": []
}
"""

MARKDOWN_WRAPPED_JSON = f"```json\n{VALID_JSON_RESPONSE}\n```"


class TestExtractJson:
    def test_parses_clean_json(self):
        data = _extract_json(VALID_JSON_RESPONSE.strip())
        assert data["overall_score"] == 78

    def test_strips_markdown_fences(self):
        data = _extract_json(MARKDOWN_WRAPPED_JSON)
        assert data["overall_score"] == 78

    def test_raises_on_gibberish(self):
        with pytest.raises(ValueError, match="Could not extract JSON"):
            _extract_json("this is not json at all !!!!")


class TestFormatResponse:
    def test_parses_valid_response(self):
        resp = format_response(VALID_JSON_RESPONSE, provider="gemini", model="gemini-2.0-flash")
        assert resp.overall_score == 78.0
        assert resp.risk_score == 35.0
        assert resp.language == "python"
        assert resp.provider == "gemini"
        assert resp.model == "gemini-2.0-flash"

    def test_parses_category_scores(self):
        resp = format_response(VALID_JSON_RESPONSE, provider="gemini", model="test")
        assert len(resp.category_scores) == 1
        assert resp.category_scores[0].category == "security"
        assert resp.category_scores[0].score == 85.0

    def test_parses_performance_findings(self):
        resp = format_response(VALID_JSON_RESPONSE, provider="gemini", model="test")
        assert len(resp.performance_findings) == 1
        finding = resp.performance_findings[0]
        assert finding.severity == "medium"
        assert finding.title == "N+1 query"
        assert finding.line_number == 42

    def test_raises_on_invalid_json(self):
        """Unparseable output must not be saved as a real (score 0) review."""
        with pytest.raises(AIProviderError):
            format_response("not valid json", provider="gemini", model="test")

    def test_coerces_and_clamps_bad_values(self):
        raw = """{"overall_score": "high", "risk_score": 250,
                  "category_scores": ["oops", {"category": "security", "score": -5}],
                  "security_findings": [{"severity": "SEVERE!!", "title": "x", "line_number": "12-14"}]}"""
        resp = format_response(raw, provider="gemini", model="test")
        assert resp.overall_score == 50 and resp.risk_score == 100
        assert [c.score for c in resp.category_scores] == [0]
        finding = resp.security_findings[0]
        assert finding.severity == "medium" and finding.line_number is None

    def test_token_counts_stored(self):
        resp = format_response(
            VALID_JSON_RESPONSE, provider="openai", model="gpt-4o",
            prompt_tokens=1000, completion_tokens=500
        )
        assert resp.prompt_tokens == 1000
        assert resp.completion_tokens == 500
