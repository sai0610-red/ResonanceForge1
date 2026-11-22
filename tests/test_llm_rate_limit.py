"""Groq rate-limit handling. No live Groq calls; sleeps are patched out."""

from __future__ import annotations

import pytest

import app.api as api
import app.core.llm as llm
from app.agents.critic import code_for_review
from app.core.config import get_settings
from app.core.llm import (
    LLMUnavailable,
    invoke_with_retry,
    rate_limit_kind,
    retry_after_seconds,
)
from tests.test_hardening import GOOD, _critique, client  # noqa: F401

GROQ_TPM = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`openai/gpt-oss-120b` in organization `org_x` service tier `on_demand` on tokens "
    "per minute (TPM): Limit 8000, Used 6526, Requested 3572. Please try again in "
    "15.735s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
)


class RateLimitError(Exception):
    status_code = 429

    def __init__(self, message: str, headers: dict | None = None):
        super().__init__(message)
        if headers is not None:
            self.response = type("R", (), {"headers": headers})()


class _Flaky:
    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def invoke(self, prompt, **_kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return {"ok": True}


@pytest.fixture
def sleeps(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(llm, "_sleep", lambda s: slept.append(s))
    monkeypatch.setattr(llm.random, "uniform", lambda a, b: (a + b) / 2)
    get_settings.cache_clear()
    yield slept
    get_settings.cache_clear()


def test_retry_after_parsing():
    assert retry_after_seconds(RateLimitError(GROQ_TPM)) == pytest.approx(15.735)
    assert retry_after_seconds(RateLimitError("try again in 1m2.5s")) == pytest.approx(62.5)
    assert retry_after_seconds(RateLimitError("try again in 450ms")) == pytest.approx(0.45)
    assert retry_after_seconds(RateLimitError("x", headers={"retry-after": "16"})) == 16.0
    assert retry_after_seconds(RateLimitError("no hint")) is None
    assert rate_limit_kind(RateLimitError(GROQ_TPM)) == "tokens_per_minute"
    assert rate_limit_kind(RateLimitError("tokens per day (TPD)")) == "tokens_per_day"


def test_rate_limit_honors_provider_hint(sleeps):
    flaky = _Flaky([RateLimitError(GROQ_TPM)])
    assert invoke_with_retry(flaky, "p")["ok"] is True
    assert flaky.calls == 2
    assert sleeps == [pytest.approx(15.735 + 1.0)]


def test_rate_limit_backoff_without_hint(sleeps):
    flaky = _Flaky([RateLimitError("rate limit")] * 3)
    assert invoke_with_retry(flaky, "p")["ok"] is True
    assert sleeps == [5.0, 15.0, 30.0]


def test_rate_limit_budget_exhausted(monkeypatch, sleeps):
    monkeypatch.setenv("LLM_RATE_LIMIT_BUDGET_SECONDS", "30")
    get_settings.cache_clear()
    flaky = _Flaky([RateLimitError("rate limit")] * 10)
    with pytest.raises(LLMUnavailable, match="rate-limited"):
        invoke_with_retry(flaky, "p")
    # 5 + 15 fit in 30s; the next 30s wait would exceed the budget.
    assert sleeps == [5.0, 15.0]
    assert flaky.calls == 3


def test_rate_limit_hint_longer_than_budget_fails_fast(monkeypatch, sleeps):
    monkeypatch.setenv("LLM_RATE_LIMIT_BUDGET_SECONDS", "60")
    get_settings.cache_clear()
    flaky = _Flaky([RateLimitError("tokens per day (TPD). Please try again in 7m12s")])
    with pytest.raises(LLMUnavailable):
        invoke_with_retry(flaky, "p")
    assert sleeps == []
    assert flaky.calls == 1


def test_fallback_model_used_after_rate_limit_exhausted(monkeypatch, sleeps):
    monkeypatch.setenv("LLM_RATE_LIMIT_BUDGET_SECONDS", "0")
    get_settings.cache_clear()
    primary = _Flaky([RateLimitError(GROQ_TPM)])
    fallback = _Flaky([])
    assert invoke_with_retry(primary, "p", fallback=fallback)["ok"] is True
    assert (primary.calls, fallback.calls) == (1, 1)


def test_fallback_not_used_for_non_rate_limit_errors(sleeps):
    primary = _Flaky([ValueError("bad request")])
    fallback = _Flaky([])
    with pytest.raises(LLMUnavailable):
        invoke_with_retry(primary, "p", fallback=fallback)
    assert fallback.calls == 0


def test_fallback_llm_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LLM_FALLBACK_MODEL", raising=False)
    get_settings.cache_clear()
    try:
        assert llm.fallback_llm(dict) is None
    finally:
        get_settings.cache_clear()


def test_wait_listener_receives_wait(sleeps):
    seen = []
    with llm.wait_listener(lambda s, r: seen.append((round(s, 2), r))):
        invoke_with_retry(_Flaky([RateLimitError(GROQ_TPM)]), "p")
    assert seen == [(16.73, "rate_limit")]


def test_code_for_review_trims_long_code():
    short = "x = 1\n"
    assert code_for_review(short, 100) == short
    long = "".join(f"line_{i} = {i}\n" for i in range(2000))
    out = code_for_review(long, 1000)
    assert len(out) < 1100
    assert out.startswith("line_0 = 0")
    assert out.rstrip().endswith("line_1999 = 1999")
    assert "lines omitted for review length" in out
    assert code_for_review(long, 0) == long


def test_stream_emits_rate_limit_status(client, monkeypatch):  # noqa: F811
    def critic(**_kw):
        llm._notify_wait(16.2, "rate_limit")
        return _critique()

    monkeypatch.setattr(api, "run_critic", critic)
    res = client.post(
        "/api/assessments/stream",
        headers=GOOD,
        json={"question": "Work-order exception triage for a manufacturer"},
    )
    assert res.status_code == 200
    body = res.text
    assert "event: status" in body
    assert "waiting_rate_limit" in body
    assert "Waiting on model rate limit (~16s)" in body
    assert "event: complete" in body
    assert body.index("event: status") < body.index("event: complete")
