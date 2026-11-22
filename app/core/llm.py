"""LLM factory with timeouts, retries, and user-facing error messages."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import random
import re
import time
from typing import Any, Callable, Iterator, Optional

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
# Bedrock (botocore ClientError) error codes.
_AWS_RATE_LIMIT_CODES = {"ThrottlingException", "TooManyRequestsException"}
_AWS_RETRYABLE_CODES = _AWS_RATE_LIMIT_CODES | {
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
}

# Backoff used for rate limits when the provider gives no hint (seconds).
_RATE_LIMIT_BACKOFF = (5.0, 15.0, 30.0)
_RATE_LIMIT_MAX_ATTEMPTS = 6
# Groq: "... Please try again in 15.735s." / "try again in 1m2.5s" / "in 450ms"
_TRY_AGAIN_RE = re.compile(
    r"try again in\s+(?:(?P<m>\d+)m)?\s*(?:(?P<ms>\d+(?:\.\d+)?)ms|(?P<s>\d+(?:\.\d+)?)s)",
    re.IGNORECASE,
)

# Optional callback so the SSE stream can tell the UI it is waiting on the model.
WaitListener = Callable[[float, str], None]
_wait_listener: contextvars.ContextVar[Optional[WaitListener]] = contextvars.ContextVar(
    "llm_wait_listener", default=None
)

# Indirection so tests can avoid real sleeps.
_sleep = time.sleep


class LLMUnavailable(Exception):
    """Raised after retries are exhausted. Message is safe to show to a client."""


def get_llm(model: str | None = None) -> Any:
    """Chat model for LLM_PROVIDER (groq | bedrock).

    Timeouts come from settings. SDK-level retries are off on both providers;
    `invoke_with_retry` owns retries so 429 handling and SSE wait events stay
    the same whichever provider is active.
    """
    settings = get_settings()
    if settings.provider == "bedrock":
        return _bedrock_llm(model or settings.bedrock_model_id)
    return ChatGroq(
        model=model or settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.temperature,
        request_timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )


def _bedrock_llm(model_id: str) -> Any:
    """ChatBedrockConverse on the default AWS credential chain (no keys in settings)."""
    try:
        from botocore.config import Config
        from langchain_aws import ChatBedrockConverse
    except ImportError as exc:  # optional dependency
        raise LLMUnavailable(
            "LLM_PROVIDER=bedrock needs the AWS extras: pip install -r requirements-aws.txt"
        ) from exc
    settings = get_settings()
    timeout = settings.llm_timeout_seconds
    return ChatBedrockConverse(
        model=model_id,
        region_name=settings.aws_region,
        temperature=settings.temperature,
        config=Config(
            connect_timeout=min(10.0, timeout),
            read_timeout=timeout,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    )


def _aws_error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        return str(code) if code else None
    return None


def fallback_llm(schema: Any) -> Any | None:
    """Structured-output runnable on LLM_FALLBACK_MODEL, or None when unset."""
    name = (get_settings().llm_fallback_model or "").strip()
    if not name:
        return None
    return get_llm(name).with_structured_output(schema)


@contextlib.contextmanager
def wait_listener(callback: WaitListener) -> Iterator[None]:
    """Report rate-limit waits (seconds, reason) to `callback` within this context."""
    token = _wait_listener.set(callback)
    try:
        yield
    finally:
        _wait_listener.reset(token)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    if _aws_error_code(exc) in _AWS_RETRYABLE_CODES:
        return True
    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS:
        return True
    return exc.__class__.__name__ in _RETRYABLE_NAMES


def is_rate_limit(exc: BaseException) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    if _aws_error_code(exc) in _AWS_RATE_LIMIT_CODES:
        return True
    return "ratelimit" in exc.__class__.__name__.lower()


def retry_after_seconds(exc: BaseException) -> float | None:
    """Provider's suggested wait: Retry-After header, else 'try again in Xs' text."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            value = headers.get("retry-after")
            if value is not None:
                return max(0.0, float(value))
        except (TypeError, ValueError):
            pass
    match = _TRY_AGAIN_RE.search(str(exc))
    if match:
        minutes = float(match.group("m") or 0)
        if match.group("ms") is not None:
            return minutes * 60 + float(match.group("ms")) / 1000.0
        return minutes * 60 + float(match.group("s") or 0)
    return None


def rate_limit_kind(exc: BaseException) -> str:
    """'tokens_per_minute', 'tokens_per_day', 'requests', or 'unknown' (no secrets)."""
    raw = str(exc).lower()
    if "(tpd)" in raw or "tokens per day" in raw:
        return "tokens_per_day"
    if "(tpm)" in raw or "tokens per minute" in raw:
        return "tokens_per_minute"
    if "(rpm)" in raw or "(rpd)" in raw or "requests per" in raw:
        return "requests"
    return "unknown"


def user_message(exc: BaseException) -> str:
    """Short, non-secret explanation for the UI / API client."""
    status = getattr(exc, "status_code", None)
    name = exc.__class__.__name__.lower()
    raw = str(exc).lower()
    if status == 429 or "rate limit" in raw or "ratelimit" in name or is_rate_limit(exc):
        return "The language model is rate-limited right now. Please wait a minute and retry."
    if (
        isinstance(exc, TimeoutError)
        or "timeout" in name
        or "timed out" in raw
        or "timeout" in raw
    ):
        return "The language model timed out. Please try again in a moment."
    return "The language model is temporarily unavailable. Please try again shortly."


def _rate_limit_wait(exc: BaseException, wait_index: int) -> float:
    hint = retry_after_seconds(exc)
    if hint is not None:
        # Small jitter so concurrent callers do not stampede the reset.
        return hint + random.uniform(0.5, 1.5)
    base = _RATE_LIMIT_BACKOFF[min(wait_index, len(_RATE_LIMIT_BACKOFF) - 1)]
    return base * random.uniform(0.8, 1.2)


def _notify_wait(seconds: float, reason: str) -> None:
    callback = _wait_listener.get()
    if callback is None:
        return
    try:
        callback(seconds, reason)
    except Exception:  # noqa: BLE001 — UI hint must never break the LLM call
        pass


def invoke_with_retry(
    runnable: Any, prompt: Any, *, fallback: Any | None = None, **kwargs: Any
) -> Any:
    """Call `runnable.invoke` with retries. Does not log secrets.

    - Rate limits (429): wait for the provider's hint (Retry-After / "try again in
      Xs"), else ~5s/15s/30s with jitter, within LLM_RATE_LIMIT_BUDGET_SECONDS.
      If still limited and `fallback` is given, try it once.
    - Other transient errors: LLM_MAX_RETRIES retries with exponential backoff.
    """
    settings = get_settings()
    other_attempts = max(1, int(settings.llm_max_retries) + 1)
    delay = max(0.0, float(settings.llm_retry_backoff_seconds))
    budget = max(0.0, float(settings.llm_rate_limit_budget_seconds))
    waited = 0.0
    rate_waits = 0
    other_failures = 0
    last: BaseException | None = None
    while True:
        try:
            return runnable.invoke(prompt, **kwargs)
        except Exception as exc:  # noqa: BLE001 — provider SDKs raise many types
            last = exc
            if not is_retryable(exc):
                break
            if is_rate_limit(exc):
                wait = _rate_limit_wait(exc, rate_waits)
                kind = rate_limit_kind(exc)
                if rate_waits + 1 >= _RATE_LIMIT_MAX_ATTEMPTS or waited + wait > budget:
                    logger.warning(
                        "llm_rate_limit_exhausted kind=%s waited_s=%.1f next_wait_s=%.1f",
                        kind,
                        waited,
                        wait,
                    )
                    break
                rate_waits += 1
                logger.warning(
                    "llm_rate_limited kind=%s wait_s=%.1f attempt=%d",
                    kind,
                    wait,
                    rate_waits,
                )
                _notify_wait(wait, "rate_limit")
                _sleep(wait)
                waited += wait
                continue
            other_failures += 1
            if other_failures >= other_attempts:
                break
            logger.warning(
                "llm_retry attempt=%d/%d error=%s",
                other_failures,
                other_attempts,
                exc.__class__.__name__,
            )
            if delay:
                _sleep(delay * (2 ** (other_failures - 1)))
    assert last is not None
    if fallback is not None and is_rate_limit(last):
        logger.warning("llm_fallback_model attempt=1")
        try:
            return fallback.invoke(prompt, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise LLMUnavailable(user_message(last)) from last
