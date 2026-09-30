"""Pull request review router."""

import asyncio
import re

from fastapi import APIRouter, Depends, Request
from github import Auth, Github, GithubException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.ai import run_review
from app.ai.base import ReviewRequest
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import GitHubError
from app.core.rate_limit import AI_LIMIT, limiter
from app.core.redis import cache_get, cache_set, get_redis
from app.middleware.auth import get_current_user
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review, ReviewType
from app.models.user import User
from app.schemas.review import PRReviewRequest
from app.services.auth_service import get_github_token
from app.services.review_service import save_failed_review, save_review

router = APIRouter(prefix="/pull-requests", tags=["pull-requests"])
settings = get_settings()

MAX_DIFF_CHARS = 80_000
MAX_PATCH_CHARS = 5_000


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Extract owner, repo, pr_number from GitHub PR URL."""
    match = re.match(r"^https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)", pr_url)
    if not match:
        raise GitHubError("Invalid PR URL")
    return match.group(1), match.group(2), int(match.group(3))


def _fetch_pr(token: str, owner: str, repo_name: str, pr_number: int) -> dict:
    """Blocking PyGithub calls — run in a worker thread. Also proves the user can see the PR."""
    try:
        gh_repo = Github(auth=Auth.Token(token)).get_repo(f"{owner}/{repo_name}")
        gh_pr = gh_repo.get_pull(pr_number)
        parts, total = [], 0
        for f in gh_pr.get_files():
            if total >= MAX_DIFF_CHARS:
                break
            section = f"--- {f.filename} (+{f.additions} -{f.deletions})\n{(f.patch or '')[:MAX_PATCH_CHARS]}\n"
            parts.append(section)
            total += len(section)
        return {
            "repo_id": gh_repo.id,
            "pr_id": gh_pr.id,
            "title": gh_pr.title,
            "body": gh_pr.body,
            "author": gh_pr.user.login,
            "base": gh_pr.base.ref,
            "head": gh_pr.head.ref,
            "head_sha": gh_pr.head.sha,
            "additions": gh_pr.additions,
            "deletions": gh_pr.deletions,
            "changed_files": gh_pr.changed_files,
            "diff": "\n".join(parts),
        }
    except GithubException as e:
        if e.status in (401, 403, 404):
            raise GitHubError("Pull request not found or you don't have access to it")
        raise GitHubError("GitHub API error while fetching the pull request")


@router.post("/review")
@limiter.limit(AI_LIMIT)
async def review_pull_request(
    request: Request,
    payload: PRReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Fetch a GitHub PR diff and generate an AI review."""
    owner, repo_name, pr_number = _parse_pr_url(payload.pr_url)

    # Fetch first: this is also the access check, so the cache below can never
    # serve a private PR to someone who cannot see it.
    pr_data = await asyncio.to_thread(_fetch_pr, get_github_token(current_user), owner, repo_name, pr_number)

    cache_key = f"{current_user.id}:{owner}/{repo_name}/{pr_number}:{pr_data['head_sha']}:{payload.detail_level}"
    cached = await cache_get(redis, "pr_review", cache_key)
    if cached:
        return cached

    review = Review(
        user_id=current_user.id,
        review_type=ReviewType.PULL_REQUEST,
        title=f"PR #{pr_number}: {pr_data['title']}",
        ai_provider=payload.ai_provider or settings.AI_PRIMARY_PROVIDER,
        ai_model="pending",
    )
    ai_request = ReviewRequest(
        review_type=ReviewType.PULL_REQUEST,
        content=pr_data["diff"],
        language="auto",
        context={
            "pr_number": pr_number,
            "pr_title": pr_data["title"],
            "author": pr_data["author"],
            "base_branch": pr_data["base"],
            "head_branch": pr_data["head"],
            "additions": pr_data["additions"],
            "deletions": pr_data["deletions"],
            "changed_files": pr_data["changed_files"],
        },
        detail_level=payload.detail_level,
    )
    try:
        ai_response = await run_review(ai_request, payload.ai_provider)
    except Exception as e:
        await save_failed_review(db, review, e)
        raise

    # Link to the imported repository when the user has one (optional)
    linked_repo_id = (
        await db.execute(
            select(Repository.id).where(
                Repository.owner_id == current_user.id,
                Repository.github_repo_id == pr_data["repo_id"],
            )
        )
    ).scalar_one_or_none()

    pr = PullRequest(
        repository_id=linked_repo_id,
        github_pr_id=pr_data["pr_id"],
        pr_number=pr_number,
        title=pr_data["title"],
        description=pr_data["body"],
        author_login=pr_data["author"],
        base_branch=pr_data["base"],
        head_branch=pr_data["head"],
        pr_url=payload.pr_url,
        additions=pr_data["additions"],
        deletions=pr_data["deletions"],
        changed_files=pr_data["changed_files"],
        risk_score=ai_response.risk_score,
    )
    db.add(pr)
    await db.flush()

    review.repository_id = linked_repo_id
    review.pull_request_id = pr.id
    await save_review(db, review, ai_response)

    result_data = {
        "review_id": str(review.id),
        "pr_number": pr_number,
        "pr_title": pr_data["title"],
        "overall_score": ai_response.overall_score,
        "risk_score": ai_response.risk_score,
        "ai_summary": ai_response.ai_summary,
        "category_scores": [
            {"category": cs.category, "score": cs.score, "summary": cs.summary, "suggestions": cs.suggestions}
            for cs in ai_response.category_scores
        ],
        "security_findings": len(ai_response.security_findings),
        "performance_findings": len(ai_response.performance_findings),
        "provider": ai_response.provider,
    }
    await cache_set(redis, "pr_review", result_data, settings.CACHE_TTL_PR_REVIEW, cache_key)
    return result_data
