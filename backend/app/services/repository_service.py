"""
Repository analysis service.
Clones repo, scans structure, feeds summarized content to AI.
We truncate/sample to stay within token limits.
"""

import asyncio
import base64
import os
import re
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import structlog
from github import Auth, Github, GithubException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.ai import run_review
from app.ai.base import ReviewRequest
from app.core.config import get_settings
from app.core.exceptions import GitHubError, NotFoundError
from app.core.redis import cache_get, cache_set
from app.models.repository import Repository, RepositoryHealth, RepositoryStatus
from app.models.review import Review, ReviewType
from app.models.user import User
from app.services.auth_service import get_github_token
from app.services.review_service import save_review

logger = structlog.get_logger()
settings = get_settings()

# File extensions we'll sample for analysis
ANALYZED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
    ".cs", ".cpp", ".c", ".rb", ".php", ".swift", ".kt", ".scala",
    ".vue", ".svelte",
}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "__pycache__", ".venv", "venv"}
PRIORITY_FILES = [
    "README.md", "package.json", "pyproject.toml", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "requirements.txt",
    "docker-compose.yml", "Dockerfile", ".env.example",
]
MAX_FILE_SIZE = 50_000   # chars per file
MAX_FILES_SAMPLED = 30
MAX_TOTAL_CHARS = 150_000
CLONE_TIMEOUT_SECONDS = 120

_REPO_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$")


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    """Return (owner, repo) from URLs like .../owner/repo, .../repo.git or .../repo/tree/main."""
    match = _REPO_URL.match(repo_url.strip())
    if not match:
        raise GitHubError("Invalid GitHub repository URL")
    return match.group(1), match.group(2)


def _fetch_repo(token: str, full_name: str) -> dict:
    """Blocking PyGithub call — run in a worker thread."""
    try:
        r = Github(auth=Auth.Token(token)).get_repo(full_name)
        return {
            "github_repo_id": r.id, "full_name": r.full_name, "name": r.name,
            "description": r.description, "url": r.html_url, "clone_url": r.clone_url,
            "default_branch": r.default_branch, "language": r.language,
            "stars": r.stargazers_count, "forks": r.forks_count,
            "open_issues": r.open_issues_count, "is_private": r.private,
        }
    except GithubException as e:
        if e.status in (401, 403, 404):
            raise GitHubError("Repository not found or you don't have access to it")
        raise GitHubError("GitHub API error while fetching the repository")


def _fetch_head_sha(token: str, full_name: str, branch: str) -> str:
    """Blocking PyGithub call — run in a worker thread."""
    try:
        return Github(auth=Auth.Token(token)).get_repo(full_name, lazy=True).get_branch(branch).commit.sha
    except GithubException:
        raise GitHubError("Could not read the repository's latest commit from GitHub")


async def fetch_head_sha(user: User, repo: Repository) -> str:
    """Latest commit SHA on the default branch — lets RAG indexing skip unchanged repos without cloning."""
    return await asyncio.to_thread(_fetch_head_sha, get_github_token(user), repo.full_name, repo.default_branch)


MAX_LISTED_REPOS = 200


def _fetch_user_repos(token: str) -> list[dict]:
    """Blocking PyGithub call — run in a worker thread."""
    try:
        repos = Github(auth=Auth.Token(token), per_page=100).get_user().get_repos(
            affiliation="owner,collaborator,organization_member", sort="updated"
        )
        return [
            {
                "full_name": r.full_name, "name": r.name, "description": r.description,
                "url": r.html_url, "language": r.language, "stars": r.stargazers_count,
                "is_private": r.private,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in repos[:MAX_LISTED_REPOS]
        ]
    except GithubException as e:
        if e.status == 401:
            raise GitHubError("GitHub authorization expired. Please sign out and sign in again.")
        raise GitHubError("GitHub API error while listing your repositories")


async def list_user_repos(user: User) -> list[dict]:
    """List GitHub repos the user can access (owned, collaborator, org), most recently updated first."""
    return await asyncio.to_thread(_fetch_user_repos, get_github_token(user))


async def import_repository(db: AsyncSession, user: User, repo_url: str) -> Repository:
    """Import repository metadata from GitHub without cloning."""
    owner, repo_name = parse_repo_url(repo_url)
    data = await asyncio.to_thread(_fetch_repo, get_github_token(user), f"{owner}/{repo_name}")

    result = await db.execute(
        select(Repository).where(
            Repository.owner_id == user.id,
            Repository.github_repo_id == data["github_repo_id"],
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    repo = Repository(owner_id=user.id, **data)
    db.add(repo)
    await db.flush()
    return repo


async def analyze_repository(
    db: AsyncSession,
    redis: aioredis.Redis,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
    force_refresh: bool = False,
) -> Repository:
    """Full repository analysis — clones, scans, calls AI, saves health snapshot + review."""
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id, Repository.owner_id == user_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")

    if not force_refresh and await cache_get(redis, "repo_analysis", str(repository_id)):
        logger.info("repo_analysis_cache_hit", repo=repo.full_name)
        return repo

    repo.status = RepositoryStatus.ANALYZING
    await db.commit()  # make the in-progress state visible to the UI

    user = await db.get(User, user_id)
    content = await _sample_repository(repo.clone_url, get_github_token(user))

    ai_response = await run_review(
        ReviewRequest(
            review_type=ReviewType.REPOSITORY,
            content=content,
            language=repo.language or "auto",
            context={"repo_name": repo.full_name, "language": repo.language, "stars": repo.stars},
        )
    )

    scores = {cs.category: cs.score for cs in ai_response.category_scores}
    db.add(
        RepositoryHealth(
            repository_id=repo.id,
            overall_score=ai_response.overall_score,
            security_score=scores.get("security", 50),
            performance_score=scores.get("performance", 50),
            maintainability_score=scores.get("maintainability", 50),
            documentation_score=scores.get("best_practices", 50),
            complexity_score=scores.get("architecture", 50),
            breakdown={
                "category_scores": [
                    {"category": cs.category, "score": cs.score, "summary": cs.summary}
                    for cs in ai_response.category_scores
                ],
                "security_findings_count": len(ai_response.security_findings),
                "performance_findings_count": len(ai_response.performance_findings),
            },
        )
    )

    # Also record it as a review so findings show up in History and Technical Debt.
    review = Review(
        user_id=user_id,
        repository_id=repo.id,
        review_type=ReviewType.REPOSITORY,
        title=repo.full_name,
        language=repo.language,
        ai_provider=ai_response.provider,
        ai_model=ai_response.model,
    )
    await save_review(db, review, ai_response)

    repo.status = RepositoryStatus.ANALYZED
    repo.last_analyzed_at = datetime.now(UTC).isoformat()
    repo.analysis_summary = {
        "overall_score": ai_response.overall_score,
        "ai_summary": ai_response.ai_summary,
        "provider": ai_response.provider,
        "model": ai_response.model,
        "review_id": str(review.id),
        "scores": scores,
    }

    await cache_set(
        redis, "repo_analysis",
        {"analyzed": True, "score": ai_response.overall_score},
        settings.CACHE_TTL_REPO_ANALYSIS,
        str(repository_id),
    )
    logger.info("repo_analysis_complete", repo=repo.full_name, score=ai_response.overall_score)
    return repo


async def _sample_repository(clone_url: str, github_token: str) -> str:
    """Shallow-clone the repo to a temp dir and sample key files."""
    async with cloned_repo(clone_url, github_token) as root:
        return await asyncio.to_thread(_extract_repo_content, str(root))


@asynccontextmanager
async def cloned_repo(clone_url: str, github_token: str) -> AsyncIterator[Path]:
    """
    Shallow-clone the repo into a temp dir, yield its resolved path, always delete it afterwards.
    The token is passed as an HTTP header through git's env-based config, so it
    never appears in the clone URL, argv (`ps`) or git's error output.
    Shared by repository analysis and RAG indexing.
    """
    basic = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
    }

    tmp_dir = tempfile.mkdtemp(prefix="devreview_")
    try:
        proc = await asyncio.create_subprocess_exec(
            # core.symlinks=false: symlinks are checked out as plain text files
            "git", "-c", "core.symlinks=false", "clone", "--depth=1", "--quiet", clone_url, tmp_dir,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=CLONE_TIMEOUT_SECONDS)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise GitHubError("Repository clone timed out")

        if proc.returncode != 0:
            logger.warning("git_clone_failed", stderr=stderr.decode(errors="replace")[:500])
            raise GitHubError("Failed to clone repository")

        yield Path(tmp_dir).resolve()
    finally:
        await asyncio.to_thread(shutil.rmtree, tmp_dir, True)


def _read_sample(root: Path, path: Path, max_chars: int = MAX_FILE_SIZE) -> str | None:
    """Read a file only if it is a regular file inside the clone (never follow symlinks out)."""
    try:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            return None
        return path.read_text(errors="replace")[:max_chars]
    except OSError:
        return None


def _extract_repo_content(repo_path: str) -> str:
    """Walk repo, sample files, build content string for AI. Blocking — run in a thread."""
    root = Path(repo_path).resolve()
    sections = []
    total_chars = 0
    files_sampled = 0

    # Prioritise important files first
    for filename in PRIORITY_FILES:
        content = _read_sample(root, root / filename)
        if content is not None:
            sections.append(f"=== {filename} ===\n{content}")
            total_chars += len(content)

    # Walk source files
    for path in sorted(root.rglob("*")):
        if files_sampled >= MAX_FILES_SAMPLED or total_chars >= MAX_TOTAL_CHARS:
            break
        if path.suffix not in ANALYZED_EXTENSIONS or any(skip in path.parts for skip in SKIP_DIRS):
            continue
        content = _read_sample(root, path)
        if content is None:
            continue
        sections.append(f"=== {path.relative_to(root)} ===\n{content}")
        total_chars += len(content)
        files_sampled += 1

    summary = f"Repository sampled {files_sampled} source files ({total_chars:,} chars)\n\n"
    return summary + "\n\n".join(sections)
