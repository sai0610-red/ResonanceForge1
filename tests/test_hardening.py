"""Production hardening: request IDs, proxy-aware rate limit, LLM retry, stream gaps.

No live Groq calls.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.api as api
from app import db
from app.core.config import get_settings
from app.core.llm import LLMUnavailable, invoke_with_retry, is_retryable, user_message
from app.core.rate_limit import client_ip
from app.models.schemas import (
    AgentRole,
    ArchitectureResult,
    CodeGenerationResult,
    CritiqueResult,
    DiagnosisResult,
    ReadinessScore,
    ResonanceReport,
)

TOKEN = "test-demo-token"
GOOD = {"X-Demo-Token": TOKEN}

FAKE_CODE = (
    "from typing import TypedDict\n"
    "from langgraph.graph import StateGraph, START, END\n\n"
    "class S(TypedDict):\n    x: int\n\n"
    "def a(state: S) -> S:\n    \"\"\"Node.\"\"\"\n    return state\n\n"
    "g = StateGraph(S)\ng.add_node('a', a)\ng.add_edge(START, 'a')\ng.add_edge('a', END)\n"
    "app = g.compile()\n"
)


def _diagnosis():
    s = ReadinessScore(score=5, reason="fake")
    return DiagnosisResult(
        access=s,
        adapt=s,
        adopt=s,
        overall_readiness="Medium",
        top_gaps=["eval testing", "data quality", "integrations"],
        summary="fake summary",
    )


def _architecture():
    return ArchitectureResult(
        recommended_agents=[AgentRole(name="Triage", responsibility="triage")],
        high_level_flow=["a"],
        rationale="r",
        estimated_complexity="Low",
    )


def _code():
    return CodeGenerationResult(code=FAKE_CODE, explanation="e")


def _critique():
    return CritiqueResult(
        strengths=["s"],
        weaknesses=["w"],
        risks=["r"],
        recommendations=["x"],
        final_verdict="Needs work",
    )


class _FakeReceive:
    async def __call__(self):
        return {"type": "http.request", "body": b"", "more_body": False}


def _request(headers=None, client_host="203.0.113.10") -> Request:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 12345),
        "server": ("test", 80),
    }
    return Request(scope, _FakeReceive())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_TOKEN", TOKEN)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "2")
    monkeypatch.setenv("MAX_SITUATION_CHARS", "4000")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("TRUSTED_PROXY", "false")
    get_settings.cache_clear()
    api.rate_limiter.reset()
    captured: dict = {"architect": None, "code_generator": None, "critic": None}

    def fake(name, result_fn):
        def _f(**kwargs):
            captured[name] = kwargs
            return result_fn()

        return _f

    monkeypatch.setattr(api, "run_diagnostician", fake("diagnostician", _diagnosis))
    monkeypatch.setattr(api, "run_architect", fake("architect", _architecture))
    monkeypatch.setattr(api, "run_code_generator", fake("code_generator", _code))
    monkeypatch.setattr(api, "run_critic", fake("critic", _critique))

    def fake_run_assessment(question, **_kwargs):
        return ResonanceReport(
            user_question=question,
            diagnosis=_diagnosis(),
            architecture=_architecture(),
            generated_code=_code(),
            critique=_critique(),
        )

    monkeypatch.setattr(api, "run_assessment", fake_run_assessment)

    with TestClient(api.app) as c:
        c.captured = captured
        yield c
    api.rate_limiter.reset()
    get_settings.cache_clear()


def test_health_assigns_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid and len(rid) >= 8
    body = r.json()
    assert body["status"] == "ok"
    assert "test-key-not-real" not in r.text


def test_request_id_is_echoed_when_valid(client):
    r = client.get("/health", headers={"X-Request-ID": "interview-run-42"})
    assert r.headers["X-Request-ID"] == "interview-run-42"


def test_request_id_rejects_junk_and_issues_new_id(client):
    r = client.get("/health", headers={"X-Request-ID": "not a valid id!!"})
    assert r.headers["X-Request-ID"] != "not a valid id!!"
    assert len(r.headers["X-Request-ID"]) >= 8


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_client_ip_ignores_forwarded_for_by_default():
    req = _request(headers={"X-Forwarded-For": "198.51.100.20, 10.0.0.1"})
    assert client_ip(req, trusted_proxy=False) == "203.0.113.10"


def test_client_ip_uses_first_forwarded_hop_when_trusted():
    req = _request(headers={"X-Forwarded-For": "198.51.100.20, 10.0.0.1"})
    assert client_ip(req, trusted_proxy=True) == "198.51.100.20"
    bare = _request()
    assert client_ip(bare, trusted_proxy=True) == "203.0.113.10"


def test_rate_limit_ignores_spoofed_xff_when_proxy_untrusted(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_TOKEN", TOKEN)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("TRUSTED_PROXY", "false")
    monkeypatch.setenv("ENV", "development")
    get_settings.cache_clear()
    api.rate_limiter.reset()

    def fake_run_assessment(question, **_kwargs):
        return ResonanceReport(
            user_question=question,
            diagnosis=_diagnosis(),
            architecture=_architecture(),
            generated_code=_code(),
            critique=_critique(),
        )

    monkeypatch.setattr(api, "run_assessment", fake_run_assessment)
    try:
        with TestClient(api.app) as c:
            body = {"question": "Triage maintenance work orders that miss SLA."}
            assert c.post("/assess", json=body, headers=GOOD).status_code == 200
            spoofed = {**GOOD, "X-Forwarded-For": "198.51.100.99"}
            r = c.post("/assess", json=body, headers=spoofed)
            assert r.status_code == 429
    finally:
        api.rate_limiter.reset()
        get_settings.cache_clear()


def test_rate_limit_uses_xff_when_trusted_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_TOKEN", TOKEN)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("TRUSTED_PROXY", "true")
    monkeypatch.setenv("ENV", "development")
    get_settings.cache_clear()
    api.rate_limiter.reset()

    def fake_run_assessment(question, **_kwargs):
        return ResonanceReport(
            user_question=question,
            diagnosis=_diagnosis(),
            architecture=_architecture(),
            generated_code=_code(),
            critique=_critique(),
        )

    monkeypatch.setattr(api, "run_assessment", fake_run_assessment)
    try:
        with TestClient(api.app) as c:
            body = {"question": "Triage maintenance work orders that miss SLA."}
            h1 = {**GOOD, "X-Forwarded-For": "198.51.100.1"}
            h2 = {**GOOD, "X-Forwarded-For": "198.51.100.2"}
            assert c.post("/assess", json=body, headers=h1).status_code == 200
            assert c.post("/assess", json=body, headers=h2).status_code == 200
            r = c.post("/assess", json=body, headers=h1)
            assert r.status_code == 429
    finally:
        api.rate_limiter.reset()
        get_settings.cache_clear()


def test_stream_passes_checklist_gap_summary(client):
    r = client.post(
        "/api/assessments/stream",
        json={"question": "Triage maintenance work orders that miss SLA."},
        headers=GOOD,
    )
    assert r.status_code == 200
    assert "event: complete" in r.text
    for name in ("architect", "code_generator", "critic"):
        kwargs = client.captured[name]
        assert kwargs is not None, name
        summary = kwargs.get("checklist_gap_summary")
        assert summary, name
        assert "ACCESS" in summary and "ADAPT" in summary and "ADOPT" in summary
        assert "eval testing" in summary


def test_sqlite_uses_wal_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        db.ensure_db()
        conn = sqlite3.connect(str(db.get_db_path()))
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        assert mode.lower() == "wal"
    finally:
        get_settings.cache_clear()


class _Flaky:
    def __init__(self, failures: int, error: Exception):
        self.failures = failures
        self.error = error
        self.calls = 0

    def invoke(self, prompt, **_kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return {"ok": True, "prompt": prompt}


class _Timeout(Exception):
    pass


def test_invoke_with_retry_recovers_after_timeouts(monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")
    get_settings.cache_clear()
    try:
        flaky = _Flaky(2, TimeoutError("timed out"))
        result = invoke_with_retry(flaky, "hello")
        assert result["ok"] is True
        assert flaky.calls == 3
    finally:
        get_settings.cache_clear()


def test_invoke_with_retry_stops_on_non_retryable(monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")
    get_settings.cache_clear()
    try:
        flaky = _Flaky(1, ValueError("bad request"))
        with pytest.raises(LLMUnavailable, match="temporarily unavailable"):
            invoke_with_retry(flaky, "hello")
        assert flaky.calls == 1
    finally:
        get_settings.cache_clear()


def test_invoke_with_retry_friendly_rate_limit(monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("LLM_RATE_LIMIT_BUDGET_SECONDS", "0")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")
    get_settings.cache_clear()

    class RateLimitError(Exception):
        status_code = 429

    try:
        flaky = _Flaky(1, RateLimitError("rate limit"))
        with pytest.raises(LLMUnavailable, match="rate-limited"):
            invoke_with_retry(flaky, "hello")
    finally:
        get_settings.cache_clear()


def test_is_retryable_and_user_message():
    class RateLimitError(Exception):
        status_code = 429

    assert is_retryable(TimeoutError("t"))
    assert is_retryable(RateLimitError("r"))
    assert not is_retryable(ValueError("no"))
    assert "timed out" in user_message(TimeoutError("t"))
    assert "rate-limited" in user_message(RateLimitError("r"))
