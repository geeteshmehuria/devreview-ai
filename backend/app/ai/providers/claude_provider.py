"""Anthropic Claude provider — secondary fallback."""

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import CHAT_MAX_OUTPUT_TOKENS, CHAT_TEMPERATURE, AIProvider, ReviewRequest, ReviewResponse, StreamDelta
from app.ai.prompts import build_prompt
from app.ai.response_formatter import format_response
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

settings = get_settings()


class ClaudeProvider(AIProvider):
    provider_name = "claude"

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise AIProviderError("ANTHROPIC_API_KEY not configured")
        self.model_name = settings.CLAUDE_MODEL
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def review(self, request: ReviewRequest) -> ReviewResponse:
        system_prompt, user_prompt = build_prompt(request)

        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = "".join(block.text for block in response.content if block.type == "text")

        return format_response(
            raw_text=raw_text,
            provider=self.provider_name,
            model=self.model_name,
            prompt_tokens=response.usage.input_tokens if response.usage else 0,
            completion_tokens=response.usage.output_tokens if response.usage else 0,
        )

    async def stream_chat(self, system: str, messages: list[dict]):
        async with self._client.messages.stream(
            model=self.model_name,
            max_tokens=CHAT_MAX_OUTPUT_TOKENS,
            temperature=CHAT_TEMPERATURE,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield StreamDelta(text=text)
            final = await stream.get_final_message()
        yield StreamDelta(prompt_tokens=final.usage.input_tokens, completion_tokens=final.usage.output_tokens)
