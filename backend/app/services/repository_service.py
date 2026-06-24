"""
Repository analysis service.
Clones repo, scans structure, feeds summarized content to AI.
We truncate/sample to stay within token limits.
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import structlog
from github import Auth, Github, GithubException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.ai import get_ai_provider
from app.ai.base import ReviewRequest
from app.core.config import get_settings
from app.core.exceptions import GitHubError, NotFoundError
from app.core.redis import cache_get, cache_set
from app.models.repository import Repository, RepositoryHealth, RepositoryStatus
from app.models.user import User

logger = structlog.get_logger()
settings = get_settings()

# File extensions we'll sample for analysis
ANALYZED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
    ".cs", ".cpp", ".c", ".rb", ".php", ".swift", ".kt", ".scala",
    ".vue", ".svelte",
}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", ".venv", "venv"}
MAX_FILE_SIZE = 50_000   # chars per file
MAX_FILES_SAMPLED = 30
MAX_TOTAL_CHARS = 150_000


async def import_repository(
    db: AsyncSession,
    user_id: str,
    repo_url: str,
    github_token: str,
) -> Repository:
    """Import repository metadata from GitHub without cloning."""
    # Parse github.com/owner/repo
    parts = repo_url.rstrip("/").split("/")
    if len(parts) < 5:
        raise GitHubError(f"Invalid GitHub URL: {repo_url}")
    owner, repo_name = parts[-2], parts[-1]

    try:
        gh = Github(auth=Auth.Token(github_token))
        gh_repo = gh.get_repo(f"{owner}/{repo_name}")
    except GithubException as e:
        raise GitHubError(f"GitHub API error: {e.data.get('message', str(e))}")

    # Check if already imported
    result = await db.execute(
        select(Repository).where(
            Repository.owner_id == uuid.UUID(user_id),
            Repository.github_repo_id == gh_repo.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    repo = Repository(
        owner_id=uuid.UUID(user_id),
        github_repo_id=gh_repo.id,
        full_name=gh_repo.full_name,
        name=gh_repo.name,
        description=gh_repo.description,
        url=gh_repo.html_url,
        clone_url=gh_repo.clone_url,
        default_branch=gh_repo.default_branch,
        language=gh_repo.language,
        stars=gh_repo.stargazers_count,
        forks=gh_repo.forks_count,
        open_issues=gh_repo.open_issues_count,
        is_private=gh_repo.private,
    )
    db.add(repo)
    await db.flush()
    return repo


async def analyze_repository(
    db: AsyncSession,
    redis: aioredis.Redis,
    repository_id: str,
    user_id: str,
    force_refresh: bool = False,
) -> Repository:
    """Full repository analysis — clones, scans, calls AI, saves health snapshot."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == uuid.UUID(repository_id),
            Repository.owner_id == uuid.UUID(user_id),
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")

    # Cache check
    cache_key = f"repo:{repository_id}"
    if not force_refresh:
        cached = await cache_get(redis, "repo_analysis", repository_id)
        if cached:
            logger.info("repo_analysis_cache_hit", repo=repo.full_name)
            return repo

    repo.status = RepositoryStatus.ANALYZING
    await db.flush()

    try:
        # Get user's GitHub token
        user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = user_result.scalar_one()

        # Sample repository content
        content = await _sample_repository(repo.clone_url, user.github_access_token)

        provider = get_ai_provider()
        ai_request = ReviewRequest(
            review_type="repository",
            content=content,
            language=repo.language or "auto",
            context={
                "repo_name": repo.full_name,
                "language": repo.language,
                "stars": repo.stars,
            },
        )
        ai_response = await provider.review(ai_request)

        # Extract sub-scores from category_scores
        score_map = {cs.category: cs.score for cs in ai_response.category_scores}

        health = RepositoryHealth(
            repository_id=repo.id,
            overall_score=ai_response.overall_score,
            security_score=score_map.get("security", 50),
            performance_score=score_map.get("performance", 50),
            maintainability_score=score_map.get("maintainability", 50),
            documentation_score=score_map.get("best_practices", 50),
            complexity_score=score_map.get("architecture", 50),
            breakdown={
                "category_scores": [
                    {"category": cs.category, "score": cs.score, "summary": cs.summary}
                    for cs in ai_response.category_scores
                ],
                "security_findings_count": len(ai_response.security_findings),
                "performance_findings_count": len(ai_response.performance_findings),
            },
        )
        db.add(health)

        repo.status = RepositoryStatus.ANALYZED
        repo.analysis_summary = {
            "overall_score": ai_response.overall_score,
            "ai_summary": ai_response.ai_summary,
            "provider": ai_response.provider,
            "model": ai_response.model,
        }
        repo.last_analyzed_at = str(uuid.uuid4())  # placeholder

        # Cache for TTL
        await cache_set(
            redis, "repo_analysis",
            {"analyzed": True, "score": ai_response.overall_score},
            settings.CACHE_TTL_REPO_ANALYSIS,
            repository_id,
        )

        logger.info("repo_analysis_complete", repo=repo.full_name, score=ai_response.overall_score)

    except Exception as e:
        repo.status = RepositoryStatus.FAILED
        logger.error("repo_analysis_failed", repo=repo.full_name, error=str(e))
        raise

    return repo


async def _sample_repository(clone_url: str, github_token: str) -> str:
    """
    Clone repo to temp dir and sample key files.
    We don't send the entire codebase — we sample strategically.
    """
    import asyncio

    # Inject token into clone URL for private repos
    auth_url = clone_url.replace("https://", f"https://x-token:{github_token}@")

    tmp_dir = tempfile.mkdtemp(prefix="devreview_")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", "--quiet", auth_url, tmp_dir,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            raise GitHubError(f"Git clone failed: {stderr.decode()[:500]}")

        return _extract_repo_content(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _extract_repo_content(repo_path: str) -> str:
    """Walk repo, sample files, build content string for AI."""
    root = Path(repo_path)
    sections = []
    total_chars = 0
    files_sampled = 0

    # Prioritise important files first
    priority_files = [
        "README.md", "package.json", "pyproject.toml", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle", "requirements.txt",
        "docker-compose.yml", "Dockerfile", ".env.example",
    ]

    for filename in priority_files:
        path = root / filename
        if path.exists():
            try:
                content = path.read_text(errors="replace")[:MAX_FILE_SIZE]
                sections.append(f"=== {filename} ===\n{content}")
                total_chars += len(content)
            except Exception:
                pass

    # Walk source files
    for path in sorted(root.rglob("*")):
        if files_sampled >= MAX_FILES_SAMPLED or total_chars >= MAX_TOTAL_CHARS:
            break
        if path.is_dir():
            continue
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.suffix not in ANALYZED_EXTENSIONS:
            continue

        try:
            content = path.read_text(errors="replace")[:MAX_FILE_SIZE]
            rel_path = path.relative_to(root)
            sections.append(f"=== {rel_path} ===\n{content}")
            total_chars += len(content)
            files_sampled += 1
        except Exception:
            pass

    summary = f"Repository sampled {files_sampled} source files ({total_chars:,} chars)\n\n"
    return summary + "\n\n".join(sections)
