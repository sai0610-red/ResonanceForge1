"""LLM factory with timeouts, retries, and user-facing error messages."""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_groq import ChatGroq

from app.core.config import get_settings

logger = logging.getLogger("resonanceforge.llm")

# Retry transient provider/network failures. Never retry on auth or bad requests.
_RETRYABLE_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "ConnectError",
    "ConnectTimeout",
    "InternalServerError",
    "PoolTimeout",
    "RateLimitError",
    "ReadTimeout",
    "ServiceUnavailableError",
    "TimeoutError",
    "WriteTimeout",
}
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class LLMUnavailable(Exception):
    """Raised after retries are exhausted. Message is safe to show to a client."""


def get_llm() -> ChatGroq:
    """Return a ChatGroq client. Timeouts come from settings; retries are handled here."""
    settings = get_settings()
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.temperature,
        request_timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS:
        return True
    return exc.__class__.__name__ in _RETRYABLE_NAMES


def user_message(exc: BaseException) -> str:
    """Short, non-secret explanation for the UI / API client."""
    status = getattr(exc, "status_code", None)
    name = exc.__class__.__name__.lower()
    raw = str(exc).lower()
    if status == 429 or "rate limit" in raw or "ratelimit" in name:
        return "The language model is rate-limited right now. Please wait a minute and retry."
    if (
        isinstance(exc, TimeoutError)
        or "timeout" in name
        or "timed out" in raw
        or "timeout" in raw
    ):
        return "The language model timed out. Please try again in a moment."
    return "The language model is temporarily unavailable. Please try again shortly."


def invoke_with_retry(runnable: Any, prompt: Any, **kwargs: Any) -> Any:
    """Call `runnable.invoke` with exponential backoff. Does not log secrets."""
    settings = get_settings()
    attempts = max(1, int(settings.llm_max_retries) + 1)
    delay = max(0.0, float(settings.llm_retry_backoff_seconds))
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return runnable.invoke(prompt, **kwargs)
        except Exception as exc:  # noqa: BLE001 — provider SDKs raise many types
            last = exc
            if attempt >= attempts or not is_retryable(exc):
                break
            logger.warning(
                "llm_retry attempt=%d/%d error=%s",
                attempt,
                attempts,
                exc.__class__.__name__,
            )
            if delay:
                time.sleep(delay * (2 ** (attempt - 1)))
    assert last is not None
    raise LLMUnavailable(user_message(last)) from last
