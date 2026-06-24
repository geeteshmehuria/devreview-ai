"""
Normalise raw AI JSON output into ReviewResponse dataclasses.
All providers funnel through here — guarantees consistent data shape regardless of model quirks.
"""

import json
import re

from app.ai.base import CategoryScore, FindingItem, ReviewResponse


def _extract_json(raw: str) -> dict:
    """
    Robustly extract JSON from AI response.
    Some models wrap JSON in markdown fences despite being told not to.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from response: {raw[:200]}...")


def _parse_findings(raw_list: list[dict]) -> list[FindingItem]:
    findings = []
    for item in raw_list or []:
        findings.append(
            FindingItem(
                severity=item.get("severity", "medium"),
                title=item.get("title", "Unknown"),
                description=item.get("description", ""),
                file_path=item.get("file_path"),
                line_number=item.get("line_number"),
                code_snippet=item.get("code_snippet"),
                recommendation=item.get("recommendation"),
                extra=item.get("extra", {}),
            )
        )
    return findings


def _parse_categories(raw_list: list[dict]) -> list[CategoryScore]:
    categories = []
    for item in raw_list or []:
        categories.append(
            CategoryScore(
                category=item.get("category", "unknown"),
                score=float(item.get("score", 50)),
                summary=item.get("summary", ""),
                suggestions=item.get("suggestions", []),
                details=item.get("details", {}),
            )
        )
    return categories


def format_response(
    raw_text: str,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> ReviewResponse:
    """
    Parse AI text output into a typed ReviewResponse.
    Never raises — falls back to a neutral response on parse errors.
    """
    try:
        data = _extract_json(raw_text)
    except ValueError:
        return ReviewResponse(
            overall_score=0,
            risk_score=100,
            ai_summary="⚠️ Failed to parse AI response. Please try again.",
            language="unknown",
            provider=provider,
            model=model,
            raw_response=raw_text,
        )

    return ReviewResponse(
        overall_score=float(data.get("overall_score", 50)),
        risk_score=float(data.get("risk_score", 50)),
        ai_summary=data.get("ai_summary", ""),
        language=data.get("language", "unknown"),
        category_scores=_parse_categories(data.get("category_scores", [])),
        security_findings=_parse_findings(data.get("security_findings", [])),
        performance_findings=_parse_findings(data.get("performance_findings", [])),
        code_smells=_parse_findings(data.get("code_smells", [])),
        technical_debt=_parse_findings(data.get("technical_debt", [])),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        provider=provider,
        model=model,
        raw_response=data,
    )
