"""
Retrieval eval: does the right file come back for known questions?

For each question in devreview_questions.json we retrieve the top chunks and find the rank of the
first chunk whose file is one of the expected files.
  hit@5 — share of questions with an expected file in the top 5
  MRR   — mean of 1/rank (0 when no expected file is in the top RAG_TOP_K); rewards rank 1 over rank 4

Runs vector-only and hybrid on the same questions (query embeddings are computed once), and
prints the best similarity of a few off-topic questions to help choose RAG_MIN_SIMILARITY.

Usage (backend container, repo already indexed):
  python -m app.rag.eval.run_eval --repo-id <uuid>
  python -m app.rag.eval.run_eval --repo-name owner/repo
"""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.repository import IndexStatus, Repository
from app.rag.embedder import GeminiEmbedder
from app.rag.retriever import retrieve

QUESTIONS = Path(__file__).with_name("devreview_questions.json")
OFF_TOPIC = [
    "What is the capital of France?",
    "How do I bake sourdough bread at home?",
    "How does the Kubernetes operator autoscale GPU pods?",
]
HIT_AT = 5
EVAL_DIR = "backend/app/rag/eval/"


class CachedEmbedder:
    """
    Embed each question once, reuse it for both modes, and keep the vectors in a file: re-running
    the eval after a retrieval change then costs no embedding quota (free tier: 1000/day).
    """

    def __init__(self, inner: GeminiEmbedder, path: Path):
        self.inner, self.path = inner, path
        self.cache = json.loads(path.read_text()) if path.exists() else {}

    async def embed_query(self, text: str) -> list[float]:
        if text not in self.cache:
            self.cache[text] = await self.inner.embed_query(text)
            self.path.write_text(json.dumps(self.cache))
        return self.cache[text]


def first_hit_rank(files: list[str], expected: list[str]) -> int | None:
    # The eval folder itself is indexed too, and its JSON pairs every question with its answer file —
    # counting it would leak the answers, so it's ignored when ranking.
    files = [f for f in files if not f.startswith(EVAL_DIR)]
    return next((i for i, f in enumerate(files, start=1) if f in expected), None)


async def main(repo_id: str | None, repo_name: str | None, cache: Path) -> None:
    questions = json.loads(QUESTIONS.read_text())
    embedder = CachedEmbedder(GeminiEmbedder(), cache)
    top_k = get_settings().RAG_TOP_K

    async with AsyncSessionLocal() as db:
        stmt = select(Repository).where(Repository.index_status == IndexStatus.INDEXED)
        stmt = stmt.where(Repository.id == repo_id) if repo_id else stmt.where(Repository.full_name == repo_name)
        repo = (await db.execute(stmt)).scalar_one()

        results: dict[str, list[int | None]] = {"vector": [], "hybrid": []}
        sims: list[float] = []
        for q in questions:
            for mode in results:
                r = await retrieve(db, repo.id, repo.owner_id, q["question"], embedder, mode=mode, top_k=top_k)
                results[mode].append(first_hit_rank([c.file_path for c in r.chunks], q["expected_files"]))
            sims.append(r.best_similarity or 0.0)

        off_topic = []
        for text in OFF_TOPIC:
            r = await retrieve(db, repo.id, repo.owner_id, text, embedder, mode="hybrid", top_k=top_k)
            off_topic.append((text, r.best_similarity or 0.0))

    def fmt(rank: int | None) -> str:
        return "—" if rank is None else (f"**{rank}**" if rank <= HIT_AT else str(rank))

    print(f"Repository: {repo.full_name} · {repo.chunk_count} chunks · top_k={top_k}\n")
    print("| # | Question | Vector rank | Hybrid rank | Best sim |")
    print("|---|---|---|---|---|")
    for q, v, h, s in zip(questions, results["vector"], results["hybrid"], sims):
        print(f"| {q['id']} | {q['question']} | {fmt(v)} | {fmt(h)} | {s:.3f} |")

    print("\n| Mode | hit@5 | MRR |")
    print("|---|---|---|")
    for mode, ranks in results.items():
        hit = sum(1 for r in ranks if r is not None and r <= HIT_AT) / len(ranks)
        mrr = sum(1 / r for r in ranks if r is not None) / len(ranks)
        print(f"| {mode} | {hit:.2f} ({sum(1 for r in ranks if r and r <= HIT_AT)}/{len(ranks)}) | {mrr:.3f} |")

    print(f"\nOn-topic best similarity: min {min(sims):.3f} · mean {sum(sims) / len(sims):.3f}")
    for text, s in off_topic:
        print(f"Off-topic best similarity: {s:.3f}  ({text})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--repo-id")
    group.add_argument("--repo-name")
    parser.add_argument("--cache", type=Path, default=Path("/tmp/rag_eval_query_vectors.json"),
                        help="query-embedding cache file (only valid for the same embedding model)")
    args = parser.parse_args()
    asyncio.run(main(args.repo_id, args.repo_name, args.cache))
