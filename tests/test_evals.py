"""The eval harness runs offline in CI and actually fails when an invariant breaks."""

from __future__ import annotations

import json

import pytest

from evals import run as harness

ENV_KEYS = (
    "DATA_DIR",
    "DEMO_TOKEN",
    "GROQ_API_KEY",
    "RATE_LIMIT_PER_HOUR",
    "UPLOAD_RATE_LIMIT_PER_HOUR",
    "ENV",
    "LOG_LEVEL",
)


@pytest.fixture
def isolated_env(monkeypatch):
    # harness.main writes os.environ; monkeypatch restores these afterwards.
    for key in ENV_KEYS:
        monkeypatch.setenv(key, "")
    monkeypatch.delenv("EVAL_LIVE", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    yield
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_all_golden_cases_load():
    cases = harness.load_cases()
    names = [c.name for c in cases]
    assert len(cases) >= 12
    for must in ("red-river", "ennis", "parker-food-group", "optex-systems"):
        assert any(must in n for n in names)


def test_build_checklist_specs():
    assert len(harness.build_checklist({"all": 3})) == 15
    per_dim = harness.build_checklist(
        {"access": [1] * 5, "adapt": [2] * 5, "adopt": [3] * 5}
    )
    assert [a["value"] for a in per_dim] == [1] * 5 + [2] * 5 + [3] * 5
    with pytest.raises(ValueError):
        harness.build_checklist({"access": [1], "adapt": [1] * 5, "adopt": [1] * 5})


def test_offline_run_passes_and_writes_summary(isolated_env, tmp_path):
    code = harness.main(["--out", str(tmp_path)])
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert code == 0, (tmp_path / "summary.md").read_text()
    assert summary["mode"] == "offline" and summary["ok"]
    assert summary["checks"] == summary["checks_passed"] > 50
    assert "| 01-red-river | PASS |" in (tmp_path / "summary.md").read_text()


def test_harness_fails_on_wrong_golden_score(isolated_env, tmp_path, monkeypatch):
    real = harness.load_cases

    def tampered(selected=None):
        cases = real(["01-red-river"])
        cases[0].expected["scores"] = {"access": 9, "adapt": 9, "adopt": 9}
        return cases

    monkeypatch.setattr(harness, "load_cases", tampered)
    assert harness.main(["--out", str(tmp_path)]) == 1
    summary = json.loads((tmp_path / "summary.json").read_text())
    failed = [c["check"] for c in summary["results"][0]["checks"] if not c["ok"]]
    assert failed == ["rubric_scores"]


def test_harness_flags_low_readiness_marked_ready(isolated_env, tmp_path, monkeypatch):
    real = harness.load_cases

    def tampered(selected=None):
        cases = real(["06-edge-all-ones"])
        cases[0].stub["critique"]["final_verdict"] = "Ready for pilot"
        return cases

    monkeypatch.setattr(harness, "load_cases", tampered)
    assert harness.main(["--out", str(tmp_path)]) == 1
    summary = json.loads((tmp_path / "summary.json").read_text())
    failed = [c["check"] for c in summary["results"][0]["checks"] if not c["ok"]]
    assert failed == ["verdict_vs_readiness"]
