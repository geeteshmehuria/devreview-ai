"""Pull request review router."""

import re
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.exceptions import GitHubError, NotFoundError
from app.core.redis import get_redis, cache_get, cache_set
from app.middleware.auth import get_current_user
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review, ReviewStatus, ReviewType
from app.models.user import User
from app.ai import get_ai_provider
from app.ai.base import ReviewRequest
from app.core.config import get_settings
from app.schemas.review import PRReviewRequest

router = APIRouter(prefix="/pull-requests", tags=["pull-requests"])
settings = get_settings()


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Extract owner, repo, pr_number from GitHub PR URL."""
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        raise GitHubError(f"Invalid PR URL: {pr_url}")
    return match.group(1), match.group(2), int(match.group(3))


@router.post("/review")
async def review_pull_request(
    payload: PRReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Fetch a GitHub PR diff and generate an AI review."""
    owner, repo_name, pr_number = _parse_pr_url(payload.pr_url)

    # Cache check
    cache_key = f"{owner}/{repo_name}/{pr_number}"
    cached = await cache_get(redis, "pr_review", cache_key)
    if cached:
        return cached

    # Fetch PR from GitHub
    from github import Auth, Github, GithubException
    try:
        gh = Github(auth=Auth.Token(current_user.github_access_token or ""))
        gh_repo = gh.get_repo(f"{owner}/{repo_name}")
        gh_pr = gh_repo.get_pull(pr_number)
    except GithubException as e:
        raise GitHubError(f"GitHub API error: {e.data.get('message', str(e))}")

    # Get diff content (sampled)
    files = list(gh_pr.get_files())
    diff_content = _build_diff_content(files)

    # AI review
    provider = get_ai_provider(payload.ai_provider)
    ai_request = ReviewRequest(
        review_type="pull_request",
        content=diff_content,
        language="auto",
        context={
            "pr_number": pr_number,
            "pr_title": gh_pr.title,
            "author": gh_pr.user.login,
            "base_branch": gh_pr.base.ref,
            "head_branch": gh_pr.head.ref,
            "additions": gh_pr.additions,
            "deletions": gh_pr.deletions,
            "changed_files": gh_pr.changed_files,
        },
        detail_level=payload.detail_level,
    )
    ai_response = await provider.review(ai_request)

    # Find or create linked repository record
    repo_result = await db.execute(
        select(Repository).where(
            Repository.owner_id == current_user.id,
            Repository.github_repo_id == gh_repo.id,
        )
    )
    linked_repo = repo_result.scalar_one_or_none()

    # Save PR record
    pr = PullRequest(
        repository_id=linked_repo.id if linked_repo else None,
        github_pr_id=gh_pr.id,
        pr_number=pr_number,
        title=gh_pr.title,
        description=gh_pr.body,
        author_login=gh_pr.user.login,
        base_branch=gh_pr.base.ref,
        head_branch=gh_pr.head.ref,
        pr_url=payload.pr_url,
        additions=gh_pr.additions,
        deletions=gh_pr.deletions,
        changed_files=gh_pr.changed_files,
        risk_score=ai_response.risk_score,
    )
    db.add(pr)
    await db.flush()

    # Create review record
    review = Review(
        user_id=current_user.id,
        repository_id=linked_repo.id if linked_repo else None,
        pull_request_id=pr.id,
        review_type=ReviewType.PULL_REQUEST,
        status=ReviewStatus.COMPLETED,
        title=f"PR #{pr_number}: {gh_pr.title}",
        ai_provider=ai_response.provider,
        ai_model=ai_response.model,
        overall_score=ai_response.overall_score,
        risk_score=ai_response.risk_score,
        ai_summary=ai_response.ai_summary,
        prompt_tokens=ai_response.prompt_tokens,
        completion_tokens=ai_response.completion_tokens,
    )
    db.add(review)

    result_data = {
        "pr_number": pr_number,
        "pr_title": gh_pr.title,
        "overall_score": ai_response.overall_score,
        "risk_score": ai_response.risk_score,
        "ai_summary": ai_response.ai_summary,
        "category_scores": [
            {"category": cs.category, "score": cs.score, "summary": cs.summary}
            for cs in ai_response.category_scores
        ],
        "security_findings": len(ai_response.security_findings),
        "performance_findings": len(ai_response.performance_findings),
        "provider": ai_response.provider,
    }

    await cache_set(redis, "pr_review", result_data, settings.CACHE_TTL_PR_REVIEW, cache_key)
    return result_data


def _build_diff_content(files: list, max_chars: int = 80_000) -> str:
    """Build a readable diff string from GitHub PR files."""
    parts = []
    total = 0
    for f in files:
        if total >= max_chars:
            break
        header = f"--- {f.filename} (+{f.additions} -{f.deletions})\n"
        patch = f.patch or ""
        section = header + patch[:5000] + "\n"
        parts.append(section)
        total += len(section)
    return "\n".join(parts)
