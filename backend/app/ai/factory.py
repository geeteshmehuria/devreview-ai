"""
AI provider factory with automatic fallback chain.
Gemini → OpenAI → Claude (preferred provider first).
A provider is skipped when its key is missing, and the next one is tried when
its API call fails or returns unusable output.
"""

from collections.abc import AsyncIterator
from dataclasses import replace

import structlog

from app.ai.base import AIProvider, ReviewRequest, ReviewResponse, StreamDelta
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


def _ordered(preferred: str | None) -> list[str]:
    primary = preferred if preferred in FALLBACK_CHAIN else settings.AI_PRIMARY_PROVIDER
    return [primary] + [p for p in FALLBACK_CHAIN if p != primary]


def _no_provider_error() -> AIProviderError:
    return AIProviderError(
        "No AI provider is configured. Set at least one of: "
        "GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY"
    )


async def run_chat_stream(system: str, messages: list[dict]) -> AsyncIterator[StreamDelta]:
    """
    Stream a chat answer through the fallback chain. A provider may be swapped only BEFORE the
    first token reaches the user: after that, switching would splice two different answers
    together, so a mid-stream failure is raised instead.
    """
    configured = False
    for name in _ordered(None):
        provider = _get_provider(name)
        if provider is None:
            continue
        configured = True
        started = False
        try:
            async for delta in provider.stream_chat(system, messages):
                started = started or bool(delta.text)
                yield replace(delta, provider=provider.provider_name, model=provider.model_name)
            return
        except Exception as e:  # GeneratorExit/CancelledError (client went away) are BaseException: not caught
            if started:
                logger.warning("ai_chat_failed_mid_stream", provider=name, error=str(e))
                raise AIProviderError("The AI provider failed while answering. Please try again.") from e
            logger.warning("ai_chat_provider_failed", provider=name, error=str(e))

    if not configured:
        raise _no_provider_error()
    raise AIProviderError("All AI providers failed. Please try again later.")


async def run_chat(system: str, messages: list[dict]) -> str:
    """Non-streaming chat (e.g. query rewriting) — same fallback chain, collected into one string."""
    return "".join([delta.text async for delta in run_chat_stream(system, messages)])


async def run_review(request: ReviewRequest, preferred: str | None = None) -> ReviewResponse:
    """Run the review on the preferred provider, falling back through the chain on any failure."""
    ordered = _ordered(preferred)

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
        raise _no_provider_error()
    raise AIProviderError("All AI providers failed. Please try again later.")
