"""LLM_PROVIDER selection (groq default | bedrock) and Bedrock error handling.

No network: Bedrock clients are built but never invoked, or are mocked.
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

import app.api as api
import app.core.llm as llm
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch, tmp_path):
    for key in ("LLM_PROVIDER", "BEDROCK_MODEL_ID", "AWS_REGION", "LLM_FALLBACK_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ENV", "development")
    # Fake static credentials so boto3 can build a client offline. Never used.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client_error(code: str, status: int = 400) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "x"}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "Converse",
    )


def test_default_provider_is_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    s = get_settings()
    assert s.provider == "groq" and s.active_model == "openai/gpt-oss-120b"
    assert type(llm.get_llm()).__name__ == "ChatGroq"


def test_bedrock_provider_builds_converse_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "Bedrock")  # case-insensitive
    monkeypatch.setenv("BEDROCK_MODEL_ID", "openai.gpt-oss-120b-1:0")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    get_settings.cache_clear()
    with mock.patch("langchain_aws.ChatBedrockConverse") as cls:
        llm.get_llm()
    kwargs = cls.call_args.kwargs
    assert kwargs["model"] == "openai.gpt-oss-120b-1:0"
    assert kwargs["region_name"] == "us-east-1"
    assert kwargs["temperature"] == 0.2
    cfg = kwargs["config"]
    assert cfg.read_timeout == 45
    assert cfg.retries["max_attempts"] == 1  # retries live in invoke_with_retry
    assert get_settings().active_model == "openai.gpt-oss-120b-1:0"


def test_bedrock_real_class_accepts_our_kwargs(monkeypatch):
    """Instantiate the real ChatBedrockConverse (no request is sent)."""
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    get_settings.cache_clear()
    from langchain_aws import ChatBedrockConverse

    from app.models.schemas import CritiqueResult

    model = llm.get_llm()
    assert isinstance(model, ChatBedrockConverse)
    assert model.model_id == "openai.gpt-oss-120b-1:0"
    assert model.region_name == "us-west-2"
    assert model.with_structured_output(CritiqueResult) is not None


def test_bedrock_fallback_model_uses_same_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "openai.gpt-oss-20b-1:0")
    get_settings.cache_clear()
    with mock.patch("langchain_aws.ChatBedrockConverse") as cls:
        llm.fallback_llm(dict)
    assert cls.call_args.kwargs["model"] == "openai.gpt-oss-20b-1:0"


def test_bedrock_without_extras_gives_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    get_settings.cache_clear()
    monkeypatch.setitem(sys.modules, "langchain_aws", None)
    with pytest.raises(llm.LLMUnavailable, match="requirements-aws.txt"):
        llm.get_llm()


def test_unknown_provider_fails_startup(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    s = get_settings()
    assert "LLM_PROVIDER must be one of" in s.llm_config_error()
    with pytest.raises(ValueError):
        s.validate_for_startup()


def test_config_errors_per_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    assert "GROQ_API_KEY" in get_settings().llm_config_error()
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    get_settings.cache_clear()
    assert get_settings().llm_config_error() is None  # no Groq key needed
    monkeypatch.setenv("BEDROCK_MODEL_ID", " ")
    get_settings.cache_clear()
    assert "BEDROCK_MODEL_ID" in get_settings().llm_config_error()


def test_production_bedrock_needs_demo_token_not_groq_key(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("DEMO_TOKEN", "")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError) as exc:
        get_settings().validate_for_startup()
    assert "DEMO_TOKEN" in str(exc.value) and "GROQ_API_KEY" not in str(exc.value)
    monkeypatch.setenv("DEMO_TOKEN", "t")
    get_settings.cache_clear()
    get_settings().validate_for_startup()  # does not raise


def test_bedrock_throttling_is_rate_limited_and_retried(monkeypatch):
    monkeypatch.setenv("LLM_RATE_LIMIT_BUDGET_SECONDS", "120")
    get_settings.cache_clear()
    throttled = _client_error("ThrottlingException", 429)
    assert llm.is_rate_limit(throttled) and llm.is_retryable(throttled)
    assert llm.is_retryable(_client_error("ServiceUnavailableException", 503))
    denied = _client_error("AccessDeniedException", 403)
    assert not llm.is_retryable(denied) and not llm.is_rate_limit(denied)

    sleeps: list[float] = []
    monkeypatch.setattr(llm, "_sleep", sleeps.append)
    runnable = mock.Mock()
    runnable.invoke.side_effect = [throttled, throttled, "ok"]
    assert llm.invoke_with_retry(runnable, "p") == "ok"
    assert len(sleeps) == 2


def test_bedrock_access_denied_fails_fast(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(llm, "_sleep", sleeps.append)
    runnable = mock.Mock()
    runnable.invoke.side_effect = _client_error("AccessDeniedException", 403)
    with pytest.raises(llm.LLMUnavailable):
        llm.invoke_with_retry(runnable, "p")
    assert runnable.invoke.call_count == 1 and sleeps == []


def test_health_and_assess_with_bedrock_and_no_groq_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("DEMO_TOKEN", "")
    get_settings.cache_clear()
    api.rate_limiter.reset()
    with TestClient(api.app) as c:
        h = c.get("/health").json()
        assert h["provider"] == "bedrock" and h["model"] == "openai.gpt-oss-120b-1:0"
        with mock.patch.object(api, "_load_grounding", side_effect=RuntimeError("reached")):
            # Gets past the provider check (no 500 for the missing Groq key).
            with pytest.raises(RuntimeError, match="reached"):
                c.post("/assess", json={"question": "q"})
    api.rate_limiter.reset()


def test_client_ip_last_hop_for_alb():
    from starlette.requests import Request

    from app.core.rate_limit import client_ip

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-forwarded-for", b"6.6.6.6, 198.51.100.7")],
        "client": ("10.0.0.5", 1234),
    }
    req = Request(scope, receive)
    # A client-supplied first entry is ignored; the ALB-appended last one wins.
    assert client_ip(req, trusted_proxy=True, hop="last") == "198.51.100.7"
    assert client_ip(req, trusted_proxy=True, hop="first") == "6.6.6.6"
    assert client_ip(req, trusted_proxy=False, hop="last") == "10.0.0.5"
