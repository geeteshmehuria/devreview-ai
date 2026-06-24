"""
AI provider factory with automatic fallback chain.
Gemini → OpenAI → Claude.
If the primary is unavailable (missing key or API error), we cascade to the next.
"""

import structlog

from app.ai.base import AIProvider
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

logger = structlog.get_logger()
settings = get_settings()

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
        logger.warning("ai_provider_init_failed", provider=name, error=str(e))
    return None


def get_ai_provider(preferred: str | None = None) -> AIProvider:
    """
    Return an AI provider, falling back through the chain if the preferred
    provider is not configured.

    Fallback order: gemini → openai → claude
    """
    primary = preferred or settings.AI_PRIMARY_PROVIDER
    fallback_chain = ["gemini", "openai", "claude"]

    # Put preferred first, then remaining in default order
    ordered = [primary] + [p for p in fallback_chain if p != primary]

    for name in ordered:
        # Reuse cached instances (they hold connection pools)
        if name in _provider_cache:
            return _provider_cache[name]

        provider = _make_provider(name)
        if provider:
            _provider_cache[name] = provider
            if name != primary:
                logger.info("ai_provider_fallback", requested=primary, using=name)
            return provider

    raise AIProviderError(
        "No AI provider is configured. Set at least one of: "
        "GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY"
    )
