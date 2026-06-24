"""
Prompt builder — constructs structured prompts for code review tasks.
Keeping prompts centralised means we can A/B test and version them independently of the provider.
"""

from app.ai.base import ReviewRequest

SYSTEM_PROMPT = """You are DevReview AI, an expert senior software engineer and security specialist.
You perform thorough, actionable code reviews with the precision of a principal engineer at a top tech company.

Your reviews are:
- Specific: Point to exact lines and patterns, not vague generalities
- Actionable: Every finding includes a concrete fix
- Prioritised: Critical issues first, cosmetic issues last
- Educational: Explain the *why* behind each recommendation

You always respond in valid JSON matching the specified schema."""


def build_code_review_prompt(request: ReviewRequest) -> str:
    context_str = ""
    if request.context.get("filename"):
        context_str += f"\nFile: {request.context['filename']}"
    if request.context.get("pr_title"):
        context_str += f"\nPR Title: {request.context['pr_title']}"
    if request.context.get("repo_name"):
        context_str += f"\nRepository: {request.context['repo_name']}"

    detail_instructions = {
        "brief": "Provide a concise review focusing only on critical issues.",
        "detailed": "Provide a comprehensive review covering all categories.",
        "comprehensive": (
            "Provide an exhaustive review covering every aspect of code quality, "
            "security, performance, architecture, and best practices."
        ),
    }.get(request.detail_level, "Provide a comprehensive review covering all categories.")

    return f"""Review the following {request.language} code and respond with a JSON object matching this exact schema:

{{
  "overall_score": <number 0-100>,
  "risk_score": <number 0-100, where 100 is highest risk>,
  "language": "<detected language>",
  "ai_summary": "<executive summary in markdown, 3-5 paragraphs>",
  "category_scores": [
    {{
      "category": "security",
      "score": <0-100>,
      "summary": "<one paragraph>",
      "suggestions": ["<actionable suggestion>", ...],
      "details": {{}}
    }},
    {{
      "category": "performance",
      "score": <0-100>,
      "summary": "<one paragraph>",
      "suggestions": ["<actionable suggestion>", ...],
      "details": {{}}
    }},
    {{
      "category": "readability",
      "score": <0-100>,
      "summary": "<one paragraph>",
      "suggestions": ["<actionable suggestion>", ...],
      "details": {{}}
    }},
    {{
      "category": "maintainability",
      "score": <0-100>,
      "summary": "<one paragraph>",
      "suggestions": ["<actionable suggestion>", ...],
      "details": {{}}
    }},
    {{
      "category": "architecture",
      "score": <0-100>,
      "summary": "<one paragraph>",
      "suggestions": ["<actionable suggestion>", ...],
      "details": {{}}
    }},
    {{
      "category": "best_practices",
      "score": <0-100>,
      "summary": "<one paragraph>",
      "suggestions": ["<actionable suggestion>", ...],
      "details": {{}}
    }}
  ],
  "security_findings": [
    {{
      "severity": "critical|high|medium|low|info",
      "title": "<short title>",
      "description": "<detailed description>",
      "file_path": "<path or null>",
      "line_number": <number or null>,
      "code_snippet": "<relevant code or null>",
      "recommendation": "<specific fix>",
      "extra": {{"cwe_id": "<CWE-xxx or null>"}}
    }}
  ],
  "performance_findings": [
    {{
      "severity": "high|medium|low",
      "title": "<short title>",
      "description": "<detailed description>",
      "file_path": "<path or null>",
      "line_number": <number or null>,
      "code_snippet": "<relevant code or null>",
      "recommendation": "<specific fix>",
      "extra": {{"impact": "<estimated impact>"}}
    }}
  ],
  "code_smells": [
    {{
      "severity": "high|medium|low",
      "title": "<smell type: Long Method/God Class/etc>",
      "description": "<what makes this a smell>",
      "file_path": "<path or null>",
      "line_number": <number or null>,
      "code_snippet": "<relevant code or null>",
      "recommendation": "<refactoring approach>",
      "extra": {{}}
    }}
  ],
  "technical_debt": [
    {{
      "severity": "critical|high|medium|low",
      "title": "<debt item>",
      "description": "<why this is debt>",
      "file_path": "<path or null>",
      "line_number": null,
      "code_snippet": null,
      "recommendation": "<how to address it>",
      "extra": {{"estimated_hours": <number>, "category": "<architecture|testing|documentation|etc>"}}
    }}
  ]
}}

{detail_instructions}
{context_str}

CODE TO REVIEW:
```{request.language}
{request.content}
```

Respond with ONLY the JSON object, no markdown fences, no explanation outside the JSON."""


def build_repository_prompt(request: ReviewRequest) -> str:
    return f"""Analyse this repository structure and produce a health assessment.
Respond with the standard review JSON schema.

Focus on:
1. Architecture patterns and design decisions
2. Security posture (dependency vulnerabilities, secret exposure, auth patterns)
3. Performance characteristics
4. Code quality and maintainability
5. Documentation coverage
6. Dependency health

REPOSITORY STRUCTURE AND KEY FILES:
{request.content}

Respond with ONLY the JSON object matching the review schema."""


def build_pr_review_prompt(request: ReviewRequest) -> str:
    pr_context = request.context
    return f"""Review this GitHub Pull Request diff.

PR: #{pr_context.get('pr_number')} — {pr_context.get('pr_title', 'Untitled')}
Author: {pr_context.get('author', 'Unknown')}
Base: {pr_context.get('base_branch', 'main')} ← Head: {pr_context.get('head_branch', 'feature')}
Files changed: {pr_context.get('changed_files', 0)} | +{pr_context.get('additions', 0)} -{pr_context.get('deletions', 0)}

Focus on:
1. Bugs and regressions introduced by this change
2. Security vulnerabilities in changed code
3. Breaking changes and backward compatibility
4. Test coverage for new code
5. Performance impact

DIFF:
{request.content}

Respond with ONLY the JSON object matching the review schema."""


PROMPT_BUILDERS = {
    "code_snippet": build_code_review_prompt,
    "file_upload": build_code_review_prompt,
    "repository": build_repository_prompt,
    "pull_request": build_pr_review_prompt,
}


def build_prompt(request: ReviewRequest) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the given request type."""
    builder = PROMPT_BUILDERS.get(request.review_type, build_code_review_prompt)
    return SYSTEM_PROMPT, builder(request)
