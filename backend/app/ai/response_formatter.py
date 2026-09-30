"""
Normalise raw AI JSON output into ReviewResponse dataclasses.
All providers funnel through here — guarantees consistent data shape regardless of model quirks.
"""

import json
import re

from app.ai.base import CategoryScore, FindingItem, ReviewResponse
from app.core.exceptions import AIProviderError

SEVERITIES = {"critical", "high", "medium", "low", "info"}


def _extract_json(raw: str) -> dict:
    """
    Robustly extract a JSON object from AI response.
    Some models wrap JSON in markdown fences despite being told not to.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()

    for candidate in (cleaned, (re.search(r"\{.*\}", cleaned, re.DOTALL) or [None])[0]):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    raise ValueError(f"Could not extract JSON from response: {raw[:200]}...")


def _num(value, default: float = 50.0, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        return min(hi, max(lo, float(value)))
    except (TypeError, ValueError):
        return default


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value) -> str | None:
    return str(value) if value not in (None, "", "null") else None


def _dicts(raw) -> list[dict]:
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _parse_findings(raw_list) -> list[FindingItem]:
    findings = []
    for item in _dicts(raw_list):
        severity = str(item.get("severity", "medium")).lower()
        extra = item.get("extra")
        findings.append(
            FindingItem(
                severity=severity if severity in SEVERITIES else "medium",
                title=str(item.get("title") or "Untitled finding"),
                description=str(item.get("description") or ""),
                file_path=_str_or_none(item.get("file_path")),
                line_number=_int_or_none(item.get("line_number")),
                code_snippet=_str_or_none(item.get("code_snippet")),
                recommendation=_str_or_none(item.get("recommendation")),
                extra=extra if isinstance(extra, dict) else {},
            )
        )
    return findings


def _parse_categories(raw_list) -> list[CategoryScore]:
    categories = []
    for item in _dicts(raw_list):
        suggestions = item.get("suggestions")
        details = item.get("details")
        categories.append(
            CategoryScore(
                category=str(item.get("category") or "unknown")[:50],
                score=_num(item.get("score")),
                summary=str(item.get("summary") or ""),
                suggestions=[str(s) for s in suggestions] if isinstance(suggestions, list) else [],
                details=details if isinstance(details, dict) else {},
            )
        )
    return categories


def build_response(
    data: dict,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> ReviewResponse:
    """Build a typed ReviewResponse from an already-parsed JSON object (also used for cache hits)."""
    return ReviewResponse(
        overall_score=_num(data.get("overall_score")),
        risk_score=_num(data.get("risk_score")),
        ai_summary=str(data.get("ai_summary") or ""),
        language=str(data.get("language") or "unknown")[:100],
        category_scores=_parse_categories(data.get("category_scores")),
        security_findings=_parse_findings(data.get("security_findings")),
        performance_findings=_parse_findings(data.get("performance_findings")),
        code_smells=_parse_findings(data.get("code_smells")),
        technical_debt=_parse_findings(data.get("technical_debt")),
        prompt_tokens=prompt_tokens or 0,
        completion_tokens=completion_tokens or 0,
        provider=provider,
        model=model,
        raw_response=data,
    )


def format_response(
    raw_text: str,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> ReviewResponse:
    """
    Parse AI text output into a typed ReviewResponse.
    Raises AIProviderError when the output is not usable JSON, so the caller can
    fall back to another provider or mark the review as failed.
    """
    try:
        data = _extract_json(raw_text)
    except ValueError as e:
        raise AIProviderError(f"{provider} returned an unreadable response") from e
    return build_response(data, provider, model, prompt_tokens, completion_tokens)
