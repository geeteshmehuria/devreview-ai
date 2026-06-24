"""
Google Gemini AI provider (primary).
Uses gemini-2.0-flash for speed/cost balance; can be upgraded to gemini-1.5-pro.
"""

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import AIProvider, ReviewRequest, ReviewResponse
from app.ai.prompts import build_prompt
from app.ai.response_formatter import format_response
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

settings = get_settings()


class GeminiProvider(AIProvider):
    provider_name = "gemini"
    model_name = "gemini-2.0-flash-exp"

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise AIProviderError("GEMINI_API_KEY not configured")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=genai.GenerationConfig(
                temperature=0.1,      # Low temp = more deterministic, consistent JSON
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def review(self, request: ReviewRequest) -> ReviewResponse:
        system_prompt, user_prompt = build_prompt(request)

        # Gemini uses a single content stream; prepend system as first message
        chat = self._model.start_chat(history=[])
        response = await chat.send_message_async(
            f"{system_prompt}\n\n{user_prompt}"
        )

        raw_text = response.text
        usage = response.usage_metadata

        return format_response(
            raw_text=raw_text,
            provider=self.provider_name,
            model=self.model_name,
            prompt_tokens=getattr(usage, "prompt_token_count", 0),
            completion_tokens=getattr(usage, "candidates_token_count", 0),
        )

    async def health_check(self) -> bool:
        try:
            model = genai.GenerativeModel(self.model_name)
            response = await model.generate_content_async("Reply with: ok")
            return bool(response.text)
        except Exception:
            return False
