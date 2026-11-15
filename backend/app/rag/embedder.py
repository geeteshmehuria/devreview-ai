"""
Gemini embedding client for RAG.

Deliberately NOT part of the Gemini → OpenAI → Claude fallback chain: vectors from different models
live in different spaces, so mixing them would silently break search. If Gemini fails, indexing
fails and can be retried.
"""

import math

import structlog
from google import genai
from google.genai import errors, types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.exceptions import EmbeddingError
from app.models.code_chunk import EMBEDDING_DIM

logger = structlog.get_logger()
settings = get_settings()

BATCH_SIZE = 100  # max texts per batchEmbedContents request
DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "CODE_RETRIEVAL_QUERY"  # Gemini's task type for natural-language → code search


def _is_retryable(exc: BaseException) -> bool:
    """Rate limits (429) and server errors are worth retrying; bad requests are not."""
    if isinstance(exc, errors.APIError):
        return exc.code == 429 or exc.code >= 500
    return isinstance(exc, (TimeoutError, ConnectionError))


def normalize(vector: list[float]) -> list[float]:
    """Scale to unit length. gemini-embedding-001 only normalises full 3072-dim output, not 768."""
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise EmbeddingError("Embedding model returned a zero vector")
    return [v / norm for v in vector]


class GeminiEmbedder:
    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise EmbeddingError("GEMINI_API_KEY is required for repository chat (embeddings use Gemini only)")
        self.model = settings.EMBEDDING_MODEL
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed code chunks, in batches. Sequential on purpose: the free tier is rate-limited."""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            vectors.extend(await self._embed_batch(texts[i:i + BATCH_SIZE], DOCUMENT_TASK))
            logger.info("embedding_progress", done=len(vectors), total=len(texts))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed_batch([text], QUERY_TASK))[0]

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=2, min=4, max=60),  # 4s, 8s, 16s, 32s, 60s
        reraise=True,
    )
    async def _embed_batch(self, texts: list[str], task_type: str) -> list[list[float]]:
        response = await self._client.aio.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIM),
        )
        embeddings = response.embeddings or []
        if len(embeddings) != len(texts) or any(len(e.values or []) != EMBEDDING_DIM for e in embeddings):
            raise EmbeddingError("Embedding response did not match the request")
        return [normalize(e.values) for e in embeddings]
