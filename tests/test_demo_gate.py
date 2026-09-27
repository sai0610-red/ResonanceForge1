"""Demo token gate, public endpoints, 422 limits, 429 rate limit, production guard.

No LLM calls: agent functions are monkeypatched. DATA_DIR is a temp dir.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.api as api
from app.core.config import get_settings
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
        access=s, adapt=s, adopt=s, overall_readiness="Medium",
        top_gaps=["g1", "g2", "g3"], summary="fake summary",
    )


def _architecture():
    return ArchitectureResult(
        recommended_agents=[AgentRole(name="Triage", responsibility="triage")],
        high_level_flow=["a"], rationale="r", estimated_complexity="Low",
    )


def _code():
    return CodeGenerationResult(code=FAKE_CODE, explanation="e")


def _critique():
    return CritiqueResult(
        strengths=["s"], weaknesses=["w"], risks=["r"], recommendations=["x"],
        final_verdict="Needs work",
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_TOKEN", TOKEN)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "2")
    monkeypatch.setenv("MAX_SITUATION_CHARS", "100")
    monkeypatch.setenv("ENV", "development")
    get_settings.cache_clear()
    api.rate_limiter.reset()

    calls = {"llm": 0}

    def fake(result_fn):
        def _f(**_kwargs):
            calls["llm"] += 1
            return result_fn()
        return _f

    monkeypatch.setattr(api, "run_diagnostician", fake(_diagnosis))
    monkeypatch.setattr(api, "run_architect", fake(_architecture))
    monkeypatch.setattr(api, "run_code_generator", fake(_code))
    monkeypatch.setattr(api, "run_critic", fake(_critique))

    def fake_run_assessment(question, **_kwargs):
        calls["llm"] += 1
        return ResonanceReport(
            user_question=question, diagnosis=_diagnosis(), architecture=_architecture(),
            generated_code=_code(), critique=_critique(),
        )

    monkeypatch.setattr(api, "run_assessment", fake_run_assessment)

    with TestClient(api.app) as c:
        c.calls = calls
        yield c
    api.rate_limiter.reset()
    get_settings.cache_clear()


def _body(question="Triage maintenance work orders that miss SLA."):
    return {"question": question}


def _stream_id(client) -> str:
    r = client.post("/api/assessments/stream", json=_body(), headers=GOOD)
    assert r.status_code == 200
    assert "event: complete" in r.text
    import json as _json

    for block in r.text.split("\n\n"):
        if block.startswith("event: complete"):
            data = _json.loads(block.split("data: ", 1)[1])
            return data["id"]
    raise AssertionError("no complete event")


def test_gated_endpoints_401_without_token(client):
    assert client.post("/assess", json=_body()).status_code == 401
    assert client.post("/api/assessments/stream", json=_body()).status_code == 401
    assert client.post("/assess", json=_body(), headers={"X-Demo-Token": "wrong"}).status_code == 401
    assert client.get("/api/assessments").status_code == 401
    assert client.get("/api/assessments/some-id/pilot.zip").status_code == 401
    assert client.calls["llm"] == 0


def test_public_endpoints_stay_public(client):
    h = client.get("/health")
    assert h.status_code == 200
    body = h.json()
    assert set(body) == {"status", "env", "db_ok", "model"}
    assert body["db_ok"] is True
    assert "test-key-not-real" not in h.text and TOKEN not in h.text
    assert client.get("/").status_code == 200
    assert client.get("/api/checklist").status_code == 200
    assert client.get("/static/styles.css").status_code == 200

    rid = _stream_id(client)
    assert client.get(f"/r/{rid}").status_code == 200
    rep = client.get(f"/api/reports/{rid}")
    assert rep.status_code == 200
    sc = rep.json()["report"]["scaffold_check"]
    assert sc["ok"] is True and sc["has_stategraph"] and sc["has_compile"]


def test_pilot_zip_requires_token(client):
    rid = _stream_id(client)
    assert client.get(f"/api/assessments/{rid}/pilot.zip").status_code == 401
    ok = client.get(f"/api/assessments/{rid}/pilot.zip", headers=GOOD)
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "application/zip"
    assert client.get("/api/assessments", headers=GOOD).status_code == 200


def test_422_on_empty_or_too_long(client):
    for q in ("", "   \n\t "):
        assert client.post("/assess", json=_body(q), headers=GOOD).status_code == 422
        assert client.post("/api/assessments/stream", json=_body(q), headers=GOOD).status_code == 422
    too_long = "x" * 101
    r = client.post("/assess", json=_body(too_long), headers=GOOD)
    assert r.status_code == 422
    assert "100" in r.json()["detail"]
    assert client.post("/api/assessments/stream", json=_body(too_long), headers=GOOD).status_code == 422
    assert client.calls["llm"] == 0


def test_429_after_limit_with_retry_after(client):
    assert client.post("/assess", json=_body(), headers=GOOD).status_code == 200
    _stream_id(client)  # both endpoints share the per-IP budget
    before = client.calls["llm"]
    r = client.post("/assess", json=_body(), headers=GOOD)
    assert r.status_code == 429
    retry = int(r.headers["Retry-After"])
    assert 0 < retry <= 3600
    assert client.post("/api/assessments/stream", json=_body(), headers=GOOD).status_code == 429
    assert client.calls["llm"] == before


def test_scaffold_check_on_sync_response(client):
    r = client.post("/assess", json=_body(), headers=GOOD)
    assert r.status_code == 200
    assert r.json()["scaffold_check"]["ok"] is True


def test_no_token_configured_means_open(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_TOKEN", "")
    monkeypatch.setenv("ENV", "development")
    get_settings.cache_clear()
    try:
        with TestClient(api.app) as c:
            assert c.get("/api/assessments").status_code == 200
    finally:
        get_settings.cache_clear()


def test_production_refuses_to_start_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("DEMO_TOKEN", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DEMO_TOKEN"):
            with TestClient(api.app):
                pass
        monkeypatch.setenv("DEMO_TOKEN", TOKEN)
        monkeypatch.setenv("GROQ_API_KEY", "")
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            with TestClient(api.app):
                pass
    finally:
        get_settings.cache_clear()
