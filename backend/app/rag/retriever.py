"""
Hybrid retrieval for repo chat, scoped to one repository of one owner.

1. Vector search  — embedding <=> question embedding (cosine), top 20. Finds code by meaning.
2. Keyword search — tsvector @@ tsquery, top 20. Finds exact identifiers, file names, error strings.
3. Reciprocal Rank Fusion (k=60) merges the two rankings → top RAG_TOP_K chunks.
4. Saved review findings for the repo, full-text searched → top 3 extra context items.

All SQL here is PostgreSQL-only (pgvector, full-text search); tests mock these functions.
Every query joins `repositories` and filters on owner_id, so a chunk can never leak across users
even if a caller forgets its own ownership check.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, Integer, bindparam, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.config import get_settings
from app.models.code_chunk import EMBEDDING_DIM, CodeChunk
from app.models.repository import Repository
from app.models.review import CodeSmell, PerformanceFinding, Review, SecurityFinding, TechnicalDebt
from app.rag.embedder import GeminiEmbedder
from app.rag.indexer import split_identifier

settings = get_settings()

CANDIDATES = 20  # per search method, before fusion
RRF_K = 60       # standard constant from the RRF paper; damps the advantage of rank 1 vs rank 2
FINDINGS_K = 3


@dataclass
class RetrievedChunk:
    id: uuid.UUID
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None
    language: str
    content: str
    similarity: float | None  # cosine similarity; None if it was only found by keyword search
    score: float              # RRF score


@dataclass
class RetrievedFinding:
    kind: str  # security | performance | code_smell | technical_debt
    severity: str
    title: str
    description: str
    file_path: str | None
    line: int | None
    recommendation: str | None


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    findings: list[RetrievedFinding] = field(default_factory=list)
    best_similarity: float | None = None
    low_confidence: bool = True


# ── Query → keyword terms ─────────────────────────────────────────────────────

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "code", "do", "does", "for", "from", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "repo", "repository", "show", "that", "the",
    "this", "to", "use", "used", "uses", "what", "when", "where", "which", "who", "why", "with", "work",
    "works", "you",
}


def query_terms(question: str) -> list[str]:
    """Lowercase keywords for the tsquery: identifiers kept whole AND split (getUser → getuser, get, user)."""
    terms: list[str] = []
    for ident in re.findall(r"[A-Za-z0-9_]+", question):
        for term in [ident.lower(), *split_identifier(ident)]:
            if len(term) > 1 and term not in STOP_WORDS and term not in terms:
                terms.append(term)
    return terms


def _tsquery(terms: list[str]):
    # OR, not AND: a question rarely shares *all* its words with the code. ts_rank_cd still ranks
    # chunks that match more terms (and closer together) higher. Terms are [a-z0-9] only, so they
    # can't inject tsquery operators, and they go in as a bound parameter anyway.
    return func.to_tsquery("simple", bindparam("tsq", " | ".join(terms)))


# ── Searches (PostgreSQL only) ────────────────────────────────────────────────

def _owned_chunks(repository_id: uuid.UUID, user_id: uuid.UUID):
    return (
        select(CodeChunk)
        .options(defer(CodeChunk.embedding), defer(CodeChunk.search_text))  # don't ship 768 floats back
        .join(Repository, Repository.id == CodeChunk.repository_id)
        .where(Repository.id == repository_id, Repository.owner_id == user_id)
    )


async def vector_search(
    db: AsyncSession, repository_id: uuid.UUID, user_id: uuid.UUID, query_vector: list[float], limit: int = CANDIDATES
) -> list[tuple[CodeChunk, float]]:
    # `<=>` is pgvector's cosine-distance operator (0 = same direction); similarity = 1 - distance.
    # Spelled out with .op() because the column is a with_variant type (Text/JSON on SQLite).
    distance = CodeChunk.embedding.op("<=>", return_type=Float)(
        bindparam("qvec", query_vector, type_=Vector(EMBEDDING_DIM))
    )
    stmt = _owned_chunks(repository_id, user_id).add_columns((1 - distance).label("similarity"))
    rows = (await db.execute(stmt.order_by(distance).limit(limit))).all()
    return [(chunk, float(similarity)) for chunk, similarity in rows]


async def keyword_search(
    db: AsyncSession, repository_id: uuid.UUID, user_id: uuid.UUID, terms: list[str], limit: int = CANDIDATES
) -> list[CodeChunk]:
    tsq = _tsquery(terms)
    rank = func.ts_rank_cd(CodeChunk.search_text, tsq)
    stmt = _owned_chunks(repository_id, user_id).where(CodeChunk.search_text.op("@@")(tsq))
    return list((await db.execute(stmt.order_by(rank.desc()).limit(limit))).scalars().all())


# kind, model, title column, line column, recommendation column — the four tables differ slightly.
_FINDING_SOURCES = [
    ("security", SecurityFinding, SecurityFinding.title, SecurityFinding.line_number, SecurityFinding.recommendation),
    ("performance", PerformanceFinding, PerformanceFinding.title, PerformanceFinding.line_number,
     PerformanceFinding.recommendation),
    ("code_smell", CodeSmell, CodeSmell.smell_type, CodeSmell.line_start, CodeSmell.refactoring_suggestion),
    ("technical_debt", TechnicalDebt, TechnicalDebt.title, None, TechnicalDebt.recommendation),
]


async def search_findings(
    db: AsyncSession, repository_id: uuid.UUID, user_id: uuid.UUID, terms: list[str], limit: int = FINDINGS_K
) -> list[RetrievedFinding]:
    """
    Full-text search over saved review findings for this repo. The tsvector is computed at query
    time (no new columns on the old tables): fine for the tens/hundreds of findings a repo has.
    """
    tsq = _tsquery(terms)
    scored: list[tuple[float, RetrievedFinding]] = []
    for kind, model, title_col, line_col, rec_col in _FINDING_SOURCES:
        doc = func.to_tsvector("simple", func.concat_ws(" ", title_col, model.description, model.file_path, rec_col))
        rank = func.ts_rank_cd(doc, tsq)
        stmt = (
            select(
                model.severity, title_col.label("title"), model.description, model.file_path,
                (line_col if line_col is not None else literal(None, Integer)).label("line"),
                rec_col.label("recommendation"), rank.label("rank"),
            )
            .join(Review, Review.id == model.review_id)
            .join(Repository, Repository.id == Review.repository_id)
            .where(Repository.id == repository_id, Repository.owner_id == user_id, doc.op("@@")(tsq))
            .order_by(rank.desc())
            .limit(limit)
        )
        for row in (await db.execute(stmt)).all():
            scored.append((row.rank, RetrievedFinding(
                kind, row.severity, row.title, row.description, row.file_path, row.line, row.recommendation
            )))

    # The same finding recurs when a repo was analysed several times — keep the best-ranked copy.
    seen, results = set(), []
    for _, f in sorted(scored, key=lambda x: x[0], reverse=True):
        key = (f.kind, f.title, f.file_path)
        if key not in seen:
            seen.add(key)
            results.append(f)
    return results[:limit]


# ── Fusion ────────────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(rankings: list[list[uuid.UUID]], k: int = RRF_K) -> list[tuple[uuid.UUID, float]]:
    """
    score(doc) = Σ over rankings of 1 / (k + rank). Uses only positions, never raw scores, so a
    cosine similarity and a ts_rank (different scales) can be combined without normalising them.
    A chunk found by both methods gets two contributions and rises to the top.
    """
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


async def retrieve(
    db: AsyncSession,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
    question: str,
    embedder: GeminiEmbedder,
    *,
    mode: str = "hybrid",  # "hybrid" | "vector" (vector-only exists for the eval comparison)
    top_k: int | None = None,
) -> RetrievalResult:
    top_k = top_k or settings.RAG_TOP_K
    query_vector = await embedder.embed_query(question)
    vector_hits = await vector_search(db, repository_id, user_id, query_vector)

    by_id = {chunk.id: chunk for chunk, _ in vector_hits}
    similarity = {chunk.id: sim for chunk, sim in vector_hits}
    rankings = [[chunk.id for chunk, _ in vector_hits]]

    terms = query_terms(question)
    if mode == "hybrid" and terms:
        keyword_hits = await keyword_search(db, repository_id, user_id, terms)
        by_id.update({chunk.id: chunk for chunk in keyword_hits})
        rankings.append([chunk.id for chunk in keyword_hits])

    chunks = [
        RetrievedChunk(
            id=c.id, file_path=c.file_path, start_line=c.start_line, end_line=c.end_line,
            symbol_name=c.symbol_name, language=c.language, content=c.content,
            similarity=similarity.get(chunk_id), score=score,
        )
        for chunk_id, score in reciprocal_rank_fusion(rankings)[:top_k]
        for c in [by_id[chunk_id]]
    ]
    findings = await search_findings(db, repository_id, user_id, terms) if terms else []

    # Confidence comes from the vector side only: a keyword match on "the" proves nothing.
    best = vector_hits[0][1] if vector_hits else None
    return RetrievalResult(
        chunks=chunks,
        findings=findings,
        best_similarity=best,
        low_confidence=best is None or best < settings.RAG_MIN_SIMILARITY,
    )
