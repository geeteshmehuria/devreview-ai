"""
AI provider factory with automatic fallback chain.
Gemini → OpenAI → Claude (preferred provider first).
A provider is skipped when its key is missing, and the next one is tried when
its API call fails or returns unusable output.
"""

import structlog

from app.ai.base import AIProvider, ReviewRequest, ReviewResponse
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

logger = structlog.get_logger()
settings = get_settings()

FALLBACK_CHAIN = ("gemini", "openai", "claude")
_provider_cache: dict[str, AIProvider] = {}


def _make_provider(name: str) -> AIProvider | None:
    """Instantiate a provider by name. Returns None if not configured."""
    try:
        if name == "gemini":
            from app.ai.providers.gemini import GeminiProvider
            return GeminiProvider()
        if name == "openai":
            from app.ai.providers.openai_provider import OpenAIProvider
            return OpenAIProvider()
        if name == "claude":
            from app.ai.providers.claude_provider import ClaudeProvider
            return ClaudeProvider()
    except AIProviderError as e:
        logger.info("ai_provider_not_configured", provider=name, error=str(e))
    return None


def _get_provider(name: str) -> AIProvider | None:
    if name not in _provider_cache:
        provider = _make_provider(name)
        if provider is None:
            return None
        _provider_cache[name] = provider  # reuse instances (they hold connection pools)
    return _provider_cache[name]


async def run_review(request: ReviewRequest, preferred: str | None = None) -> ReviewResponse:
    """Run the review on the preferred provider, falling back through the chain on any failure."""
    primary = preferred if preferred in FALLBACK_CHAIN else settings.AI_PRIMARY_PROVIDER
    ordered = [primary] + [p for p in FALLBACK_CHAIN if p != primary]

    configured = False
    for name in ordered:
        provider = _get_provider(name)
        if provider is None:
            continue
        configured = True
        try:
            return await provider.review(request)
        except Exception as e:
            logger.warning("ai_provider_failed", provider=name, error=str(e))

    if not configured:
        raise AIProviderError(
            "No AI provider is configured. Set at least one of: "
            "GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY"
        )
    raise AIProviderError("All AI providers failed. Please try again later.")
