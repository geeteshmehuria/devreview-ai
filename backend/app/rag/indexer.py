"""
RAG indexing pipeline: clone → walk files → filter + redact → chunk → embed (batched) → store.

Re-indexing replaces a repository's chunks in ONE transaction: old chunks are deleted and new
ones inserted, and nothing is committed until every batch is embedded. If anything fails, the
rollback leaves the previous index intact, and chat keeps working on it while a re-index runs.
"""

import asyncio
import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import bindparam, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import GitHubError, NotFoundError
from app.models.code_chunk import CodeChunk
from app.models.repository import IndexStatus, Repository
from app.models.user import User
from app.rag.chunker import Chunk, chunk_file
from app.rag.embedder import BATCH_SIZE, GeminiEmbedder
from app.rag.sanitize import redact_secrets, should_index_content, should_index_path
from app.services.auth_service import get_github_token
from app.services.repository_service import SKIP_DIRS, _read_sample, cloned_repo, fetch_head_sha

logger = structlog.get_logger()
settings = get_settings()

# A job still "indexing" after this long was almost certainly killed (e.g. a Render restart).
STALE_INDEXING_AFTER = timedelta(minutes=30)


def can_start_indexing(repo: Repository) -> bool:
    """Allow a new run unless one is in progress — a run stuck for 30+ minutes counts as dead."""
    if repo.index_status != IndexStatus.INDEXING:
        return True
    updated = repo.updated_at
    if updated.tzinfo is None:  # SQLite returns naive UTC datetimes
        updated = updated.replace(tzinfo=UTC)
    return updated < datetime.now(UTC) - STALE_INDEXING_AFTER


def collect_chunks(root: Path, max_file_chars: int, max_chunks: int) -> list[Chunk]:
    """Walk the clone and chunk every indexable file. Blocking — run in a thread."""
    chunks: list[Chunk] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        rel_posix = rel.as_posix()
        if any(part in SKIP_DIRS for part in rel.parts) or not should_index_path(rel_posix):
            continue
        # Read one char past the limit so oversized files can be detected and skipped, not truncated.
        text = _read_sample(root, path, max_chars=max_file_chars + 1)
        if text is None or not should_index_content(text, max_file_chars):
            continue
        chunks.extend(chunk_file(rel_posix, redact_secrets(text, rel_posix)))
        if len(chunks) >= max_chunks:
            # shortcut: files are walked alphabetically, so the cap drops whatever comes last; rank
            # files (README/src first, tests/docs last) if real repos start hitting it.
            logger.warning("rag_chunk_cap_reached", cap=max_chunks)
            return chunks[:max_chunks]
    return chunks


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def split_identifier(ident: str) -> list[str]:
    """getGithubToken / get_github_token / HTTPServer → ['get','github','token'] / ['http','server']."""
    return [w.lower() for piece in ident.split("_") for w in _WORD.findall(piece)]


def search_text_for(chunk: Chunk) -> str:
    """
    Source text for the tsvector. Postgres' `simple` config lowercases words but keeps
    `getGithubToken` as one token, so we append identifiers split on camelCase and snake_case:
    a search for "github token" then matches.
    """
    # Postgres parses "lib/api/client.ts" as one file-path token, so add its parts as plain words.
    words: set[str] = {w.lower() for w in re.split(r"[/._\-]+", chunk.file_path) if len(w) > 1}
    for ident in _IDENT.findall(f"{chunk.file_path} {chunk.symbol_name or ''} {chunk.content}"):
        parts = split_identifier(ident)
        if len(parts) > 1:
            words.update(parts)
    return f"{chunk.file_path} {chunk.symbol_name or ''}\n{chunk.content}\n{' '.join(sorted(words))}"


async def _git_head_sha(root: Path) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(root), "rev-parse", "HEAD",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    sha = out.decode().strip()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GitHubError("Could not read the cloned commit")
    return sha


async def index_repository(
    db: AsyncSession,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
    embedder: GeminiEmbedder | None = None,
) -> Repository:
    """Index (or re-index) one repository. The caller commits."""
    repo = (
        await db.execute(select(Repository).where(Repository.id == repository_id, Repository.owner_id == user_id))
    ).scalar_one_or_none()
    if not repo:
        raise NotFoundError("Repository not found")
    user = await db.get(User, user_id)
    embedder = embedder or GeminiEmbedder()  # fail before cloning if Gemini isn't configured

    try:
        head = await fetch_head_sha(user, repo)
    except GitHubError as e:  # e.g. default branch renamed — just skip the shortcut
        logger.warning("rag_head_sha_unavailable", repo=repo.full_name, error=e.detail)
        head = None
    if head and head == repo.indexed_commit_sha:
        logger.info("rag_index_up_to_date", repo=repo.full_name, sha=head)
        repo.index_status = IndexStatus.INDEXED
        return repo

    # The router already committed index_status=indexing, so the UI shows progress from here on.
    async with cloned_repo(repo.clone_url, get_github_token(user)) as root:
        commit_sha = await _git_head_sha(root)
        chunks = await asyncio.to_thread(
            collect_chunks, root, settings.RAG_MAX_FILE_CHARS, settings.RAG_MAX_CHUNKS_PER_REPO
        )
    logger.info("rag_chunks_collected", repo=repo.full_name, chunks=len(chunks))

    await db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repo.id))
    # Embed and insert batch by batch, so only ~100 vectors are held in memory at a time (512 MB host).
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        vectors = await embedder.embed_documents([c.embed_text() for c in batch])
        await _insert_chunks(db, repo.id, commit_sha, batch, vectors)
        logger.info("rag_index_progress", repo=repo.full_name, done=i + len(batch), total=len(chunks))

    repo.index_status = IndexStatus.INDEXED
    repo.indexed_commit_sha = commit_sha
    repo.indexed_at = datetime.now(UTC)
    repo.chunk_count = len(chunks)
    logger.info("rag_index_complete", repo=repo.full_name, chunks=len(chunks), sha=commit_sha)
    return repo


async def _insert_chunks(
    db: AsyncSession, repository_id: uuid.UUID, commit_sha: str, chunks: list[Chunk], vectors: list[list[float]]
) -> None:
    table = CodeChunk.__table__
    if db.bind.dialect.name == "postgresql":
        # 'simple' (not 'english'): no stemming or stop words, so code identifiers stay intact.
        stmt = insert(table).values(search_text=func.to_tsvector("simple", bindparam("search_src")))
    else:  # SQLite tests: search_text is plain Text
        stmt = insert(table).values(search_text=bindparam("search_src"))
    await db.execute(stmt, [
        {
            "repository_id": repository_id,
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "symbol_name": c.symbol_name,
            "language": c.language,
            "content": c.content,
            "content_hash": hashlib.sha256(c.content.encode()).hexdigest(),
            "commit_sha": commit_sha,
            "embedding": vector,
            "search_src": search_text_for(c),
        }
        for c, vector in zip(chunks, vectors, strict=True)
    ])
