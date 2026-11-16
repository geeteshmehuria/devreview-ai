"""Google Gemini AI provider (primary) — uses the google-genai SDK."""

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import CHAT_MAX_OUTPUT_TOKENS, CHAT_TEMPERATURE, AIProvider, ReviewRequest, ReviewResponse, StreamDelta
from app.ai.prompts import build_prompt
from app.ai.response_formatter import format_response
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

settings = get_settings()


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise AIProviderError("GEMINI_API_KEY not configured")
        self.model_name = settings.GEMINI_MODEL
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def review(self, request: ReviewRequest) -> ReviewResponse:
        system_prompt, user_prompt = build_prompt(request)

        response = await self._client.aio.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,  # low temp = more deterministic, consistent JSON
                max_output_tokens=32768,  # thinking tokens count too; 8192 truncated the JSON
                response_mime_type="application/json",
            ),
        )
        usage = response.usage_metadata

        return format_response(
            raw_text=response.text or "",
            provider=self.provider_name,
            model=self.model_name,
            prompt_tokens=getattr(usage, "prompt_token_count", 0),
            completion_tokens=getattr(usage, "candidates_token_count", 0),
        )

    async def stream_chat(self, system: str, messages: list[dict]):
        contents = [
            types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
            for m in messages
        ]
        usage = None
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=CHAT_TEMPERATURE, max_output_tokens=CHAT_MAX_OUTPUT_TOKENS
            ),
        ):
            usage = chunk.usage_metadata or usage
            if chunk.text:
                yield StreamDelta(text=chunk.text)
        yield StreamDelta(
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            completion_tokens=getattr(usage, "candidates_token_count", None),
        )
