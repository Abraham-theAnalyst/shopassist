"""The only module that talks to an AI provider.

Endpoints call generate_reply() and never see which provider answered.
To add a provider (e.g. Anthropic), write a function with the same
signature as _openrouter_reply and register it in _PROVIDERS.
"""

import logging
from collections.abc import Callable
from functools import lru_cache

import openai
from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# A message in the conversation: {"role": "user" | "assistant", "content": "..."}
ChatMessage = dict[str, str]


class AIServiceError(Exception):
    """The AI couldn't produce a reply (timeout, rate limit, provider error, empty reply)."""


@lru_cache
def _openrouter_client() -> OpenAI:
    if not settings.openrouter_api_key:
        logger.error("OPENROUTER_API_KEY is not set")
        raise AIServiceError("OPENROUTER_API_KEY is not set")
    return OpenAI(
        base_url=settings.ai_base_url,
        api_key=settings.openrouter_api_key,
        timeout=settings.ai_timeout_seconds,
        # No automatic retries: they would multiply the wait time and
        # use up the free tier's daily request limit.
        max_retries=0,
    )


def _openrouter_reply(system_prompt: str, history: list[ChatMessage]) -> str:
    try:
        response = _openrouter_client().chat.completions.create(
            model=settings.ai_model,
            messages=[{"role": "system", "content": system_prompt}, *history],
            max_tokens=settings.ai_max_tokens,
        )
    except openai.APIStatusError as exc:
        # Only the status code is logged: the error body could echo the request
        logger.warning("AI provider returned an error: HTTP %s", exc.status_code)
        raise AIServiceError("provider error") from exc
    except openai.OpenAIError as exc:
        # Timeouts, connection failures, etc.
        logger.warning("AI provider call failed: %s", type(exc).__name__)
        raise AIServiceError("provider call failed") from exc

    reply = response.choices[0].message.content if response.choices else None
    if not reply or not reply.strip():
        logger.warning("AI provider returned an empty reply (model=%s)", response.model)
        raise AIServiceError("empty reply")

    # With openrouter/free, response.model is the model the router picked
    logger.info("AI reply from provider=openrouter model=%s", response.model)
    return reply.strip()


_PROVIDERS: dict[str, Callable[[str, list[ChatMessage]], str]] = {
    "openrouter": _openrouter_reply,
}


def generate_reply(system_prompt: str, history: list[ChatMessage]) -> str:
    """Send the system prompt and history to the configured provider and return the reply.

    Raises AIServiceError if no reply could be produced.
    """
    provider = _PROVIDERS.get(settings.ai_provider)
    if provider is None:
        logger.error("Unknown AI_PROVIDER: %s", settings.ai_provider)
        raise AIServiceError("unknown provider")
    return provider(system_prompt, history)
