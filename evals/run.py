"""ResonanceForge eval harness.

Runs golden cases through the real FastAPI app (upload, SSE stream, rubric,
retrieval, citation validation, scaffold check, pilot zip, 1-pager, Markdown) and
checks the deterministic parts of the output.

Offline (default): LLM calls return stubbed structured outputs, so it needs no key
and runs in CI. Live (`--live` or EVAL_LIVE=1): real model calls; slow and uses
your provider quota.

    python -m evals.run                 # offline, all cases
    python -m evals.run --case red-river --live
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
import time
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = Path(__file__).resolve().parent / "cases"
STUBS_FILE = Path(__file__).resolve().parent / "stubs" / "default.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "results"

DIMENSIONS = ("access", "adapt", "adopt")
VERDICTS = ("Ready for pilot", "Needs work", "Not ready")
CITATION_RE = re.compile(r"\[(D\d+:C\d+)\]")

# Headings every completed report must have (Markdown export: 1-pager + full report).
REQUIRED_SECTIONS = (
    "# Leadership brief",
    "## Executive verdict",
    "## Scores",
    "## Top gaps",
    "## 90-day plan",
    "## Go / No-Go",
    "# ResonanceForge Assessment Report",
    "## Diagnosis (ACCESS / ADAPT / ADOPT)",
    "## Architecture",
    "## Generated LangGraph Code",
    "## Critique",
)
REQUIRED_PILOT_FILES = ("Dockerfile", "WHAT_BREAKS_FIRST.md")

_SCHEMA_KEYS = {
    "DiagnosisResult": "diagnosis",
    "ArchitectureResult": "architecture",
    "CodeGenerationResult": "generated_code",
    "CritiqueResult": "critique",
}


# --- case loading -----------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def build_checklist(spec: Any) -> Optional[list[dict]]:
    """Case checklist spec -> API checklist list.

    {"all": 3} sets every answer; {"access": [..5], "adapt": [...], "adopt": [...]}
    sets answers per dimension in checklist order; a list is passed through.
    """
    from app.rubric.checklist import get_checklist_payload

    if spec is None:
        return None
    if isinstance(spec, list):
        return spec
    questions = get_checklist_payload()
    if "all" in spec:
        return [{"question_id": q["id"], "value": int(spec["all"])} for q in questions]
    out = []
    for dim in DIMENSIONS:
        qs = [q for q in questions if q["dimension"] == dim]
        values = spec[dim]
        if len(values) != len(qs):
            raise ValueError(f"checklist.{dim} needs {len(qs)} values")
        out.extend({"question_id": q["id"], "value": int(v)} for q, v in zip(qs, values))
    return out


@dataclass
class Case:
    name: str
    description: str
    body: dict
    documents: list[Path]
    stub: dict
    expected: dict


def load_cases(selected: Optional[list[str]] = None) -> list[Case]:
    stubs = json.loads(STUBS_FILE.read_text())
    cases = []
    for path in sorted(CASES_DIR.glob("*.json")):
        name = path.stem
        if selected and not any(s in name for s in selected):
            continue
        raw = json.loads(path.read_text())
        body: dict = {}
        if raw.get("intake_file"):
            body.update(json.loads((ROOT / raw["intake_file"]).read_text()))
        body.update(raw.get("intake") or {})
        if "checklist" in raw:
            body["checklist"] = build_checklist(raw["checklist"])
        if raw.get("document_set_id"):
            body["document_set_id"] = raw["document_set_id"]
        cases.append(
            Case(
                name=name,
                description=raw.get("description", ""),
                body=body,
                documents=[ROOT / d for d in raw.get("documents", [])],
                stub=_deep_merge(stubs, raw.get("stub") or {}),
                expected=raw.get("expected") or {},
            )
        )
    return cases


# --- stub LLM ---------------------------------------------------------------


class _StubRunnable:
    def __init__(self, schema: Any, outputs: dict, calls: list):
        self.schema = schema
        self.outputs = outputs
        self.calls = calls

    def invoke(self, prompt: Any, **_kw: Any) -> Any:
        key = _SCHEMA_KEYS[self.schema.__name__]
        self.calls.append({"agent": key, "prompt": prompt})
        return self.schema.model_validate(self.outputs[key])


class StubLLM:
    """Stands in for the chat model: `.with_structured_output(schema).invoke(...)`."""

    def __init__(self, outputs: dict, calls: list):
        self.outputs = outputs
        self.calls = calls

    def with_structured_output(self, schema: Any) -> _StubRunnable:
        return _StubRunnable(schema, self.outputs, self.calls)


def _patch_llm(stack: ExitStack, outputs: dict, calls: list) -> None:
    factory = lambda *a, **k: StubLLM(outputs, calls)  # noqa: E731
    for mod in ("diagnostician", "architect", "code_generator", "critic"):
        stack.enter_context(mock.patch(f"app.agents.{mod}.get_llm", factory))
        stack.enter_context(mock.patch(f"app.agents.{mod}.fallback_llm", lambda *_a: None))


# --- checks -----------------------------------------------------------------


@dataclass
class CaseResult:
    name: str
    description: str
    checks: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    seconds: float = 0.0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})

    @property
    def ok(self) -> bool:
        return self.error is None and all(c["ok"] for c in self.checks)


def _band(mean: float) -> str:
    return "Low" if mean < 4.5 else ("Medium" if mean < 7.5 else "High")


def _texts(report: dict) -> list[str]:
    d, a = report["diagnosis"], report["architecture"]
    out = [d[k]["reason"] for k in DIMENSIONS] + list(d["top_gaps"]) + [d["summary"]]
    out += [ag["responsibility"] for ag in a["recommended_agents"]]
    out += list(a["high_level_flow"]) + [a["rationale"]]
    return out


def check_report(
    res: CaseResult, case: Case, done: dict, md: str, zip_path: Path, live: bool = False
) -> None:
    report = done["report"]
    exp = case.expected
    d = report["diagnosis"]
    scores = {k: d[k]["score"] for k in DIMENSIONS}

    # 1. Deterministic rubric scores.
    if "scores" in exp:
        res.check("rubric_scores", scores == exp["scores"], f"got {scores}, want {exp['scores']}")
    source_llm = str(d["summary"]).startswith("Estimated without checklist")
    want_source = exp.get("diagnosis_source", "rubric")
    res.check(
        "diagnosis_source",
        source_llm == (want_source == "llm"),
        f"summary prefix says {'llm' if source_llm else 'rubric'}, want {want_source}",
    )
    if not source_llm:
        reasons_ok = all(d[k]["reason"].startswith("Checklist-driven:") for k in DIMENSIONS)
        res.check("rubric_reasons", reasons_ok, "rubric path must explain scores from answers")

    # 2. Band + verdict mapping consistency.
    mean = sum(scores.values()) / 3
    band_ok = d["overall_readiness"] == _band(mean) or source_llm
    # A model-estimated band (no checklist) is only pinned in offline mode.
    if "overall_readiness" in exp and not (source_llm and live):
        band_ok = band_ok and d["overall_readiness"] == exp["overall_readiness"]
    res.check(
        "overall_band",
        band_ok,
        f"mean {mean:.2f} -> {_band(mean)}; got {d['overall_readiness']}",
    )
    verdict = report["critique"]["final_verdict"]
    op = done.get("one_pager") or {}
    mapping_ok = (
        verdict in VERDICTS
        and op.get("go_no_go") == verdict
        and verdict in op.get("executive_verdict", "")
        and d["overall_readiness"] in op.get("executive_verdict", "")
        and f"## Go / No-Go\n\n**{verdict}**" in md
    )
    res.check("verdict_mapping", mapping_ok, f"critic={verdict!r}, 1-pager={op.get('go_no_go')!r}")
    res.check(
        "verdict_vs_readiness",
        not (d["overall_readiness"] == "Low" and verdict == "Ready for pilot"),
        f"{d['overall_readiness']} readiness with verdict {verdict!r}",
    )

    # 3. Scaffold compile check (ast.parse + compile, never exec).
    sc = report.get("scaffold_check") or {}
    want_ok = exp.get("scaffold_ok", True)
    sc_ok = sc.get("ok") is want_ok
    if want_ok:
        sc_ok = sc_ok and sc.get("has_stategraph") and sc.get("has_compile")
    res.check("scaffold_compile", sc_ok, f"ok={sc.get('ok')} error={sc.get('error')}")

    # 4. Citation validity.
    ev = report.get("evidence")
    cited_in_text = {m for t in _texts(report) for m in CITATION_RE.findall(t or "")}
    if exp.get("evidence"):
        refs = {p["ref"] for p in (ev or {}).get("passages", [])}
        cited_flags = {p["ref"] for p in (ev or {}).get("passages", []) if p["cited"]}
        res.check(
            "citations_valid",
            bool(ev) and cited_in_text <= refs and cited_in_text == cited_flags,
            f"in text {sorted(cited_in_text)}; retrieved {sorted(refs)}; flagged {sorted(cited_flags)}",
        )
        dropped = (ev or {}).get("citations_dropped", 0)
        res.check(
            "citations_dropped",
            dropped >= exp.get("min_citations_dropped", 0),
            f"dropped {dropped}",
        )
        res.check("evidence_section", "## Evidence" in md, "Markdown must include Evidence")
    else:
        res.check("no_evidence_without_docs", ev is None, f"evidence={'set' if ev else None}")

    # 5. Required report sections + pilot package.
    missing = [s for s in REQUIRED_SECTIONS if s not in md]
    res.check("report_sections", not missing, f"missing {missing}" if missing else "all present")
    pilot_ok = False
    detail = "no pilot zip"
    if report.get("pilot") and zip_path.is_file():
        with zipfile.ZipFile(zip_path) as zf:
            names = {Path(n).name for n in zf.namelist()}
        lacking = [f for f in REQUIRED_PILOT_FILES if f not in names]
        pilot_ok = not lacking
        detail = f"missing {lacking}" if lacking else f"{len(names)} files"
    res.check("pilot_package", pilot_ok, detail)


def _complete_event(text: str) -> tuple[Optional[dict], Optional[str]]:
    for block in text.split("\n\n"):
        if block.startswith("event: complete"):
            return json.loads(block.split("data: ", 1)[1]), None
        if block.startswith("event: error"):
            return None, json.loads(block.split("data: ", 1)[1]).get("detail")
    return None, "stream ended without a complete event"


def run_case(client: Any, case: Case, token: str, live: bool) -> CaseResult:
    from app.models.schemas import ResonanceReport
    from app.services.pilot_package import pilot_zip_path
    from app.services.report import to_markdown

    res = CaseResult(name=case.name, description=case.description)
    headers = {"X-Demo-Token": token}
    started = time.monotonic()
    calls: list = []
    with ExitStack() as stack:
        if not live:
            _patch_llm(stack, case.stub, calls)
        body = dict(case.body)
        if case.documents:
            files = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in case.documents]
            up = client.post("/api/documents", headers=headers, files=files)
            if up.status_code != 200:
                res.error = f"upload failed: {up.status_code} {up.text[:200]}"
                return res
            body["document_set_id"] = up.json()["document_set_id"]
        r = client.post("/api/assessments/stream", headers=headers, json=body)
        if "http_status" in case.expected:
            res.check(
                "http_status",
                r.status_code == case.expected["http_status"],
                f"got {r.status_code}, want {case.expected['http_status']}",
            )
            res.check("no_llm_call", not calls, f"{len(calls)} LLM calls")
            res.seconds = round(time.monotonic() - started, 2)
            return res
        if r.status_code != 200:
            res.error = f"HTTP {r.status_code}: {r.text[:200]}"
            return res
        done, err = _complete_event(r.text)
        if err:
            res.error = err
            return res
        report = ResonanceReport.model_validate(done["report"])
        md = to_markdown(report)
        check_report(res, case, done, md, pilot_zip_path(done["id"]), live)
        if case.documents and not live:
            arch_prompts = [c["prompt"] for c in calls if c["agent"] == "architecture"]
            text = json.dumps(arch_prompts)
            res.check("architect_prompt_has_passages", "[D1:C" in text or "[D2:C" in text, "")
    res.seconds = round(time.monotonic() - started, 2)
    return res


# --- output -----------------------------------------------------------------


def summarize(results: list[CaseResult], live: bool) -> dict:
    total = sum(len(r.checks) for r in results)
    passed = sum(1 for r in results for c in r.checks if c["ok"])
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": "live" if live else "offline",
        "cases": len(results),
        "cases_passed": sum(1 for r in results if r.ok),
        "checks": total,
        "checks_passed": passed,
        "ok": all(r.ok for r in results),
        "results": [
            {
                "case": r.name,
                "description": r.description,
                "ok": r.ok,
                "error": r.error,
                "seconds": r.seconds,
                "checks": r.checks,
            }
            for r in results
        ],
    }


def to_markdown_summary(summary: dict) -> str:
    lines = [
        f"## ResonanceForge evals ({summary['mode']})",
        "",
        f"**{summary['cases_passed']}/{summary['cases']} cases passed, "
        f"{summary['checks_passed']}/{summary['checks']} checks.**",
        "",
        "| Case | Result | Checks | Failed |",
        "|------|--------|-------:|--------|",
    ]
    for r in summary["results"]:
        failed = [c["check"] + (f" ({c['detail']})" if c["detail"] else "") for c in r["checks"] if not c["ok"]]
        if r["error"]:
            failed.insert(0, "error: " + r["error"])
        n_ok = sum(1 for c in r["checks"] if c["ok"])
        lines.append(
            f"| {r['case']} | {'PASS' if r['ok'] else 'FAIL'} | {n_ok}/{len(r['checks'])} | "
            f"{'; '.join(failed).replace('|', '/') or '-'} |"
        )
    lines.append("")
    if summary["mode"] == "offline":
        lines.append(
            "Offline mode stubs the LLM, so this checks the deterministic pipeline around "
            "the model (rubric, mapping, compile check, citation validation, report shape), "
            "not model quality."
        )
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", default=os.getenv("EVAL_LIVE") == "1")
    parser.add_argument("--case", action="append", help="substring filter; repeatable")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="directory for summary.json / summary.md")
    parser.add_argument(
        "--pause", type=float, default=float(os.getenv("EVAL_LIVE_PAUSE_SECONDS", "60")),
        help="live mode: seconds between cases (free-tier token limits)",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="rf-eval-") as tmp:
        token = "eval-token"
        os.environ["DATA_DIR"] = str(Path(tmp) / "data")
        os.environ["DEMO_TOKEN"] = token
        os.environ["RATE_LIMIT_PER_HOUR"] = "1000"
        os.environ["UPLOAD_RATE_LIMIT_PER_HOUR"] = "1000"
        os.environ["ENV"] = "development"
        os.environ.setdefault("LOG_LEVEL", "WARNING")
        if args.live:
            from app.core.config import get_settings as _gs

            if not (_gs().groq_api_key or "").strip():
                print("Live mode needs GROQ_API_KEY (or .env).", file=sys.stderr)
                return 2
        else:
            os.environ["GROQ_API_KEY"] = "offline-eval-not-a-key"

        from fastapi.testclient import TestClient

        import app.api as api
        from app.core.config import get_settings

        get_settings.cache_clear()
        api.rate_limiter.reset()
        api.upload_limiter.reset()
        cases = load_cases(args.case)
        if not cases:
            print("No cases matched.", file=sys.stderr)
            return 2
        results = []
        with TestClient(api.app) as client:
            for i, case in enumerate(cases):
                if args.live and i and "http_status" not in case.expected:
                    time.sleep(args.pause)
                try:
                    results.append(run_case(client, case, token, args.live))
                except Exception as exc:  # report, keep going
                    results.append(CaseResult(case.name, case.description, error=repr(exc)[:300]))
                r = results[-1]
                print(f"{'PASS' if r.ok else 'FAIL'}  {r.name}  ({r.seconds}s)")
        get_settings.cache_clear()

    summary = summarize(results, args.live)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    md = to_markdown_summary(summary)
    (out / "summary.md").write_text(md)
    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as fh:
            fh.write(md + "\n")
    print(f"\n{summary['cases_passed']}/{summary['cases']} cases, "
          f"{summary['checks_passed']}/{summary['checks']} checks -> {out}/summary.md")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
