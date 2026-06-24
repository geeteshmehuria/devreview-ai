"""OpenAI provider — fallback when Gemini is unavailable."""

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import AIProvider, ReviewRequest, ReviewResponse
from app.ai.prompts import build_prompt
from app.ai.response_formatter import format_response
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

settings = get_settings()


class OpenAIProvider(AIProvider):
    provider_name = "openai"
    model_name = "gpt-4o-mini"  # cost-effective; upgrade to gpt-4o for production

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise AIProviderError("OPENAI_API_KEY not configured")
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def review(self, request: ReviewRequest) -> ReviewResponse:
        system_prompt, user_prompt = build_prompt(request)

        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )

        return format_response(
            raw_text=response.choices[0].message.content or "",
            provider=self.provider_name,
            model=self.model_name,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Reply with: ok"}],
                max_tokens=5,
            )
            return bool(response.choices[0].message.content)
        except Exception:
            return False
