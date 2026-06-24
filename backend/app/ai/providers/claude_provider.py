"""Anthropic Claude provider — secondary fallback."""

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import AIProvider, ReviewRequest, ReviewResponse
from app.ai.prompts import build_prompt
from app.ai.response_formatter import format_response
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

settings = get_settings()


class ClaudeProvider(AIProvider):
    provider_name = "claude"
    model_name = "claude-3-5-haiku-20241022"  # Fast + cheap for portfolio

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise AIProviderError("ANTHROPIC_API_KEY not configured")
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def review(self, request: ReviewRequest) -> ReviewResponse:
        system_prompt, user_prompt = build_prompt(request)

        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text if response.content else ""

        return format_response(
            raw_text=raw_text,
            provider=self.provider_name,
            model=self.model_name,
            prompt_tokens=response.usage.input_tokens if response.usage else 0,
            completion_tokens=response.usage.output_tokens if response.usage else 0,
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.messages.create(
                model=self.model_name,
                max_tokens=5,
                messages=[{"role": "user", "content": "Reply with: ok"}],
            )
            return bool(response.content)
        except Exception:
            return False
