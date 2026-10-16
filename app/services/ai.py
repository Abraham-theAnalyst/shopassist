"""The only module that talks to an AI provider.

Endpoints call generate_reply() and embed_texts() and never see which
provider answered. To add a provider (e.g. Anthropic), write functions with
the same signatures as _openrouter_reply / _openrouter_embed and register
them in _PROVIDERS / _EMBEDDING_PROVIDERS.
"""

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Literal

import openai
from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# A message in the conversation: {"role": "user" | "assistant", "content": "..."}
ChatMessage = dict[str, str]


class AIServiceError(Exception):
    """The AI couldn't produce a result (timeout, rate limit, provider error, empty result)."""


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


# "document": text stored in the knowledge base. "query": a customer's question.
EmbeddingMode = Literal["document", "query"]

# Texts per embedding request. Each request counts once against the daily
# free quota, so batches are large; the knowledge base fits in one.
EMBEDDING_BATCH_SIZE = 64

# nemotron-3-embed-1b was trained with these prefixes (see its model card).
# Through an OpenAI-compatible endpoint they must be added to the text.
_NEMOTRON_PREFIXES: dict[EmbeddingMode, str] = {"query": "query: ", "document": "passage: "}


def _openrouter_embed(texts: list[str], mode: EmbeddingMode) -> list[list[float]]:
    prefix = _NEMOTRON_PREFIXES[mode] if "nemotron" in settings.embedding_model else ""
    try:
        response = _openrouter_client().embeddings.create(
            model=settings.embedding_model,
            input=[prefix + text for text in texts],
        )
    except openai.APIStatusError as exc:
        logger.warning("Embedding provider returned an error: HTTP %s", exc.status_code)
        raise AIServiceError("provider error") from exc
    except openai.OpenAIError as exc:
        logger.warning("Embedding provider call failed: %s", type(exc).__name__)
        raise AIServiceError("provider call failed") from exc

    # Results carry their position; sort so they line up with the input texts
    vectors = [item.embedding for item in sorted(response.data or [], key=lambda d: d.index)]
    if len(vectors) != len(texts) or any(not v for v in vectors):
        logger.warning("Embedding provider returned %d vectors for %d texts", len(vectors), len(texts))
        raise AIServiceError("missing embeddings")
    if any(len(v) != settings.embedding_dimensions for v in vectors):
        logger.error(
            "Embedding size %d does not match EMBEDDING_DIMENSIONS=%d",
            len(vectors[0]), settings.embedding_dimensions,
        )
        raise AIServiceError("wrong embedding size")
    return vectors


_EMBEDDING_PROVIDERS: dict[str, Callable[[list[str], EmbeddingMode], list[list[float]]]] = {
    "openrouter": _openrouter_embed,
}


def embed_texts(texts: list[str], mode: EmbeddingMode) -> list[list[float]]:
    """Embed texts with the configured provider, in as few requests as possible.

    Returns one vector per text, in the same order. Raises AIServiceError if
    any batch fails, so callers never get a partial result.
    """
    if not texts:
        return []
    provider = _EMBEDDING_PROVIDERS.get(settings.ai_provider)
    if provider is None:
        logger.error("Unknown AI_PROVIDER: %s", settings.ai_provider)
        raise AIServiceError("unknown provider")

    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        vectors.extend(provider(texts[start : start + EMBEDDING_BATCH_SIZE], mode))
    logger.info(
        "Embedded %d texts (%s) with model=%s in %d request(s)",
        len(texts), mode, settings.embedding_model,
        -(-len(texts) // EMBEDDING_BATCH_SIZE),
    )
    return vectors
