"""Retriever logic: keyword terms, RRF, hybrid vs vector, low-confidence flag. Postgres SQL is mocked."""

import uuid
from types import SimpleNamespace

import pytest

from app.rag import retriever
from app.rag.retriever import RetrievedFinding, query_terms, reciprocal_rank_fusion


def test_query_terms_drop_stop_words_and_split_identifiers():
    assert query_terms("Where is getGithubToken used?") == ["getgithubtoken", "get", "github", "token"]
    assert query_terms("How does the AI fallback chain work?") == ["ai", "fallback", "chain"]
    assert query_terms("what is it?") == []
    # Only [a-z0-9] reaches the tsquery — operators like & | ! : can't be injected.
    assert all(t.isalnum() for t in query_terms("a | b & !c:* 'drop'"))


def test_rrf_rewards_agreement_between_rankings():
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    fused = reciprocal_rank_fusion([[a, b, c], [c, d, a]])
    order = [doc for doc, _ in fused]
    assert order[0] in (a, c)                  # found by both lists → top two
    assert set(order[:2]) == {a, c}
    assert dict(fused)[a] == pytest.approx(1 / 61 + 1 / 63)
    assert reciprocal_rank_fusion([]) == []


def _chunk(path):
    return SimpleNamespace(id=uuid.uuid4(), file_path=path, start_line=1, end_line=5,
                           symbol_name=None, language="python", content="...")


class FakeEmbedder:
    async def embed_query(self, text):
        return [0.0] * 768


@pytest.fixture
def mocked_search(monkeypatch):
    vec = [_chunk("a.py"), _chunk("b.py"), _chunk("c.py")]
    kw = [_chunk("k.py"), vec[2]]
    calls = {"keyword": 0}

    async def vector_search(db, repo_id, user_id, qv, limit=20):
        return [(c, s) for c, s in zip(vec, (0.71, 0.60, 0.55))]

    async def keyword_search(db, repo_id, user_id, terms, limit=20):
        calls["keyword"] += 1
        return kw

    async def search_findings(db, repo_id, user_id, terms, limit=3):
        return [RetrievedFinding("security", "high", "Token in URL", "d", "a.py", 3, None)]

    monkeypatch.setattr(retriever, "vector_search", vector_search)
    monkeypatch.setattr(retriever, "keyword_search", keyword_search)
    monkeypatch.setattr(retriever, "search_findings", search_findings)
    return SimpleNamespace(vec=vec, kw=kw, calls=calls)


@pytest.mark.asyncio
async def test_hybrid_fuses_both_lists_and_keeps_similarity(mocked_search):
    r = await retriever.retrieve(None, uuid.uuid4(), uuid.uuid4(), "github token", FakeEmbedder(), top_k=4)
    by_path = {c.file_path: c for c in r.chunks}
    assert r.chunks[0].file_path == "c.py"     # in both rankings → first after fusion
    assert set(by_path) == {"a.py", "b.py", "c.py", "k.py"}
    assert by_path["k.py"].similarity is None  # keyword-only hit has no cosine similarity
    assert by_path["a.py"].similarity == 0.71
    assert r.findings[0].title == "Token in URL"
    assert r.best_similarity == 0.71 and not r.low_confidence


@pytest.mark.asyncio
async def test_vector_mode_skips_keyword_search(mocked_search):
    r = await retriever.retrieve(None, uuid.uuid4(), uuid.uuid4(), "github token", FakeEmbedder(), mode="vector")
    assert mocked_search.calls["keyword"] == 0
    assert [c.file_path for c in r.chunks] == ["a.py", "b.py", "c.py"]


@pytest.mark.asyncio
async def test_low_confidence_below_threshold(mocked_search, monkeypatch):
    monkeypatch.setattr(retriever.settings, "RAG_MIN_SIMILARITY", 0.8)
    r = await retriever.retrieve(None, uuid.uuid4(), uuid.uuid4(), "github token", FakeEmbedder())
    assert r.low_confidence
