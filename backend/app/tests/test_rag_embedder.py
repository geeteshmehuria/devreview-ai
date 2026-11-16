"""Embedder: normalisation, response validation, and which errors are retried."""

import math
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.core.exceptions import EmbeddingError
from app.rag import embedder as embedder_module
from app.rag.embedder import GeminiEmbedder, normalize


def _embedder(fn):
    """GeminiEmbedder without a real client or API key."""
    e = GeminiEmbedder.__new__(GeminiEmbedder)
    e.model = "gemini-embedding-001"
    e._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(embed_content=fn)))
    return e


def _response(n, dim=768):
    return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0] + [0.0] * (dim - 2)) for _ in range(n)])


def test_normalize_gives_unit_length():
    v = normalize([3.0, 4.0])
    assert v == [0.6, 0.8] and math.isclose(sum(x * x for x in v), 1.0)
    with pytest.raises(EmbeddingError):
        normalize([0.0, 0.0])


@pytest.mark.asyncio
async def test_embed_documents_batches_and_normalises(monkeypatch):
    monkeypatch.setattr(embedder_module, "BATCH_SIZE", 2)
    calls = []

    async def embed_content(model, contents, config):
        calls.append((len(contents), config.task_type, config.output_dimensionality))
        return _response(len(contents))

    vectors = await _embedder(embed_content).embed_documents(["a", "b", "c"])
    assert calls == [(2, "RETRIEVAL_DOCUMENT", 768), (1, "RETRIEVAL_DOCUMENT", 768)]
    assert len(vectors) == 3 and vectors[0][:2] == [0.6, 0.8]


@pytest.mark.asyncio
async def test_query_uses_code_retrieval_task_type():
    seen = {}

    async def embed_content(model, contents, config):
        seen["task"] = config.task_type
        return _response(1)

    await _embedder(embed_content).embed_query("where is auth?")
    assert seen["task"] == "CODE_RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_wrong_dimension_is_rejected():
    async def embed_content(model, contents, config):
        return _response(1, dim=3072)

    with pytest.raises(EmbeddingError, match="did not match"):
        await _embedder(embed_content).embed_query("q")


@pytest.mark.asyncio
async def test_daily_quota_fails_fast_without_retries():
    calls = []

    async def embed_content(model, contents, config):
        calls.append(1)
        raise errors.ClientError(429, {"error": {
            "code": 429, "status": "RESOURCE_EXHAUSTED",
            "message": "Quota exceeded: EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier",
        }})

    with pytest.raises(EmbeddingError, match="daily embedding quota"):
        await _embedder(embed_content).embed_query("q")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_bad_request_is_not_retried(monkeypatch):
    calls = []

    async def embed_content(model, contents, config):
        calls.append(1)
        raise errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "bad"}})

    with pytest.raises(errors.ClientError):
        await _embedder(embed_content).embed_query("q")
    assert len(calls) == 1
