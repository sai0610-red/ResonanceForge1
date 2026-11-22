"""FastAPI application for ResonanceForge."""

from __future__ import annotations

import hmac
import json
import logging
from pathlib import Path
from typing import Any, Generator, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.agents.architect import run_architect
from app.agents.code_generator import run_code_generator
from app.agents.critic import run_critic
from app.agents.diagnostician import run_diagnostician
from app.core.agent_log import agent_timer, configure_logging
from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.graphs.resonance_graph import run_assessment
from app.models.schemas import AssessRequest, ResonanceReport, ScaffoldCheck
from app.rubric.checklist import get_checklist_payload
from app.services.one_pager import build_one_pager, one_pager_sections
from app.services.pilot_package import attach_pilot, pilot_zip_path
from app.services.report import to_markdown
from app.services.scaffold_check import check_scaffold

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

logger = logging.getLogger("resonanceforge.api")

# Per-IP sliding window for assessment-creating endpoints (in-memory).
rate_limiter = SlidingWindowRateLimiter(window_seconds=3600)

app = FastAPI(
    title="ResonanceForge",
    description="Multi-agent AI readiness assessment platform",
    version="1.2.0",
)


@app.on_event("startup")
def _startup() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    # Raises RuntimeError (app refuses to start) in production without secrets.
    settings.validate_for_startup()
    db.ensure_db()
    logger.info(
        "startup env=%s model=%s demo_token_required=%s rate_limit_per_hour=%d data_dir=%s",
        settings.env,
        settings.groq_model,
        bool(settings.demo_token),
        settings.rate_limit_per_hour,
        settings.data_path,
    )


def require_demo_token(
    x_demo_token: Optional[str] = Header(default=None, alias="X-Demo-Token"),
) -> None:
    """When DEMO_TOKEN is set, require a matching X-Demo-Token header (401 otherwise)."""
    expected = get_settings().demo_token
    if not expected:
        return
    provided = x_demo_token or ""
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid demo token. Send it in the X-Demo-Token header.",
        )


def _client_ip(request: Request) -> str:
    return (request.client.host if request.client else None) or "unknown"


def _enforce_rate_limit(request: Request) -> None:
    limit = get_settings().rate_limit_per_hour
    allowed, retry_after = rate_limiter.check(_client_ip(request), limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: {limit} assessments per hour. "
                f"Retry in {retry_after} seconds."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _validated_question(body: AssessRequest) -> str:
    """422 on empty / whitespace or over-long situation text (before any LLM call)."""
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")
    max_chars = get_settings().max_situation_chars
    if len(question) > max_chars:
        raise HTTPException(
            status_code=422,
            detail=(
                f"question is too long ({len(question)} characters); "
                f"maximum is {max_chars}."
            ),
        )
    return question


def _intake_from_body(body: AssessRequest) -> dict[str, Optional[str]]:
    return {
        "industry": body.industry,
        "company_size": body.company_size,
        "company_name": body.company_name,
        "role_title": body.role_title,
        "primary_systems": body.primary_systems,
        "constraints": body.constraints,
        "success_metric": body.success_metric,
    }


def _checklist_from_body(body: AssessRequest) -> list | None:
    if not body.checklist:
        return None
    return body.checklist


def _ensure_groq_configured() -> None:
    if not (get_settings().groq_api_key or "").strip():
        raise HTTPException(
            status_code=500,
            detail=(
                "GROQ_API_KEY is missing. "
                "Copy .env.example to .env and set GROQ_API_KEY."
            ),
        )


def _map_assessment_error(exc: Exception) -> HTTPException:
    message = str(exc) or exc.__class__.__name__
    lower = message.lower()
    if any(
        token in lower
        for token in (
            "api key",
            "authentication",
            "unauthorized",
            "invalid api",
            "groq",
        )
    ):
        return HTTPException(
            status_code=502,
            detail=f"LLM provider error: {message}",
        )
    return HTTPException(
        status_code=502,
        detail=f"Assessment failed: {message}",
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _finalize_report(
    assessment_id: str,
    report: ResonanceReport,
    *,
    primary_systems: Optional[str] = None,
) -> ResonanceReport:
    """Attach scaffold compile-check + runnable pilot zip, then persist."""
    report = _attach_scaffold_check(report)
    report = attach_pilot(
        assessment_id, report, primary_systems=primary_systems
    )
    db.save_report(assessment_id, report)
    return report


def _attach_scaffold_check(report: ResonanceReport) -> ResonanceReport:
    """Never raises: a checker failure becomes ok=False with the error."""
    try:
        result = check_scaffold(report.generated_code.code)
    except Exception as exc:  # defensive; check_scaffold already never raises
        result = {
            "ok": False,
            "error": f"scaffold check failed: {exc.__class__.__name__}",
            "lines": 0,
            "has_stategraph": False,
            "has_compile": False,
        }
    return report.model_copy(update={"scaffold_check": ScaffoldCheck(**result)})


def _report_with_scaffold_check(report: Optional[dict]) -> Optional[dict]:
    """Backfill scaffold_check for reports stored before the field existed."""
    if not report or report.get("scaffold_check"):
        return report
    code = (report.get("generated_code") or {}).get("code")
    return {**report, "scaffold_check": check_scaffold(code)}


# --- API routes (before static mounts) ---


@app.get("/health")
def health():
    """Liveness / readiness probe (no secrets)."""
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.env,
        "db_ok": db.ping(),
        "model": settings.groq_model,
    }


@app.get("/api/checklist")
def api_checklist():
    """Return the fixed 15-question ACCESS / ADAPT / ADOPT checklist."""
    return {"questions": get_checklist_payload()}


@app.get("/api/assessments", dependencies=[Depends(require_demo_token)])
def api_list_assessments(limit: int = 50):
    """List recent assessment summaries."""
    limit = max(1, min(limit, 200))
    return db.list_assessments(limit=limit)


@app.get("/api/assessments/{assessment_id}", dependencies=[Depends(require_demo_token)])
def api_get_assessment(assessment_id: str):
    """Full assessment record, including report when completed."""
    row = db.get_by_id(assessment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "company_name": row["company_name"],
        "industry": row["industry"],
        "company_size": row["company_size"],
        "role_title": row["role_title"],
        "primary_systems": row["primary_systems"],
        "constraints": row["constraints"],
        "success_metric": row["success_metric"],
        "question": row["question"],
        "checklist": row.get("checklist"),
        "report": _report_with_scaffold_check(row.get("report")),
        "error": row.get("error"),
        "share_token": row.get("share_token"),
        "one_pager": (
            one_pager_sections(
                ResonanceReport.model_validate(row["report"]),
                company_name=row.get("company_name"),
            )
            if row.get("status") == "completed" and row.get("report")
            else None
        ),
    }


@app.get(
    "/api/assessments/{assessment_id}/pilot.zip",
    dependencies=[Depends(require_demo_token)],
)
def api_download_pilot(assessment_id: str):
    """Download the runnable Docker pilot zip for an assessment.

    The id must exist in SQLite; the zip path is derived from the stored id,
    never from raw user input.
    """
    row = db.get_by_id(assessment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pilot package not found")
    assessment_id = row["id"]
    path = pilot_zip_path(assessment_id)
    if not path.is_file():
        # Try rebuild from stored report
        if not row.get("report"):
            raise HTTPException(status_code=404, detail="Pilot package not found")
        report = ResonanceReport.model_validate(row["report"])
        report = attach_pilot(
            assessment_id,
            report,
            primary_systems=row.get("primary_systems"),
        )
        db.save_report(assessment_id, report)
        path = pilot_zip_path(assessment_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Pilot package not found")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"resonanceforge-pilot-{assessment_id}.zip",
    )


@app.get("/api/reports/{assessment_id}")
def api_public_report(assessment_id: str):
    """Public JSON for share page — completed assessments only."""
    row = db.get_by_id(assessment_id)
    if row is None or row.get("status") != "completed" or not row.get("report"):
        raise HTTPException(status_code=404, detail="Report not found")
    report = ResonanceReport.model_validate(row["report"])
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "company_name": row["company_name"],
        "industry": row["industry"],
        "company_size": row["company_size"],
        "role_title": row["role_title"],
        "primary_systems": row["primary_systems"],
        "constraints": row["constraints"],
        "success_metric": row["success_metric"],
        "question": row["question"],
        "report": _report_with_scaffold_check(row["report"]),
        "one_pager": one_pager_sections(
            report, company_name=row.get("company_name")
        ),
    }


def _run_agent(assessment_id: str, agent: str, fn, **kwargs):
    with agent_timer(assessment_id, agent):
        return fn(**kwargs)


@app.post("/api/assessments/stream", dependencies=[Depends(require_demo_token)])
def api_assess_stream(body: AssessRequest, request: Request):
    """Run assessment with SSE progress events; persist result + pilot zip."""
    question = _validated_question(body)
    _ensure_groq_configured()
    _enforce_rate_limit(request)
    intake = _intake_from_body(body)
    checklist = _checklist_from_body(body)

    assessment_id = db.create_assessment(
        question=question,
        status="running",
        checklist=checklist,
        **intake,
    )

    def stream() -> Generator[str, None, None]:
        try:
            yield _sse(
                "step",
                {
                    "step": 1,
                    "name": "diagnostician",
                    "label": "Diagnosing readiness",
                    "id": assessment_id,
                },
            )
            diagnosis = _run_agent(
                assessment_id,
                "diagnostician",
                run_diagnostician,
                question=question,
                checklist=checklist,
                **intake,
            )
            yield _sse(
                "step",
                {
                    "step": 1,
                    "name": "diagnostician",
                    "label": "Diagnosing readiness",
                    "id": assessment_id,
                    "partial": {"diagnosis": diagnosis.model_dump()},
                },
            )

            yield _sse(
                "step",
                {
                    "step": 2,
                    "name": "architect",
                    "label": "Designing architecture",
                    "id": assessment_id,
                },
            )
            architecture = _run_agent(
                assessment_id,
                "architect",
                run_architect,
                question=question,
                diagnosis=diagnosis,
                **intake,
            )
            yield _sse(
                "step",
                {
                    "step": 2,
                    "name": "architect",
                    "label": "Designing architecture",
                    "id": assessment_id,
                    "partial": {"architecture": architecture.model_dump()},
                },
            )

            yield _sse(
                "step",
                {
                    "step": 3,
                    "name": "code_generator",
                    "label": "Generating LangGraph code",
                    "id": assessment_id,
                },
            )
            generated_code = _run_agent(
                assessment_id,
                "code_generator",
                run_code_generator,
                question=question,
                diagnosis=diagnosis,
                architecture=architecture,
                **intake,
            )
            yield _sse(
                "step",
                {
                    "step": 3,
                    "name": "code_generator",
                    "label": "Generating LangGraph code",
                    "id": assessment_id,
                    "partial": {
                        "generated_code": {
                            "language": generated_code.language,
                            "framework": generated_code.framework,
                            "explanation": generated_code.explanation,
                        }
                    },
                },
            )

            yield _sse(
                "step",
                {
                    "step": 4,
                    "name": "critic",
                    "label": "Critiquing solution",
                    "id": assessment_id,
                },
            )
            critique = _run_agent(
                assessment_id,
                "critic",
                run_critic,
                question=question,
                diagnosis=diagnosis,
                architecture=architecture,
                generated_code=generated_code,
                **intake,
            )
            yield _sse(
                "step",
                {
                    "step": 4,
                    "name": "critic",
                    "label": "Critiquing solution",
                    "id": assessment_id,
                    "partial": {"critique": critique.model_dump()},
                },
            )

            report = ResonanceReport(
                user_question=question,
                diagnosis=diagnosis,
                architecture=architecture,
                generated_code=generated_code,
                critique=critique,
            )
            report = _finalize_report(
                assessment_id,
                report,
                primary_systems=intake.get("primary_systems"),
            )
            yield _sse(
                "complete",
                {
                    "id": assessment_id,
                    "report": report.model_dump(),
                    "one_pager": one_pager_sections(
                        report, company_name=intake.get("company_name")
                    ),
                },
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            try:
                db.update_status(assessment_id, "failed", error=message)
            except Exception:
                pass
            yield _sse("error", {"detail": message, "id": assessment_id})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/assess", dependencies=[Depends(require_demo_token)])
def assess(body: AssessRequest, request: Request):
    """Run the four-agent ResonanceForge assessment (sync; persists + pilot)."""
    question = _validated_question(body)
    _ensure_groq_configured()
    _enforce_rate_limit(request)
    intake = _intake_from_body(body)
    checklist = _checklist_from_body(body)

    assessment_id = db.create_assessment(
        question=question,
        status="running",
        checklist=checklist,
        **intake,
    )

    try:
        report = run_assessment(
            question=question,
            checklist=checklist,
            assessment_id=assessment_id,
            **intake,
        )
        report = _finalize_report(
            assessment_id,
            report,
            primary_systems=intake.get("primary_systems"),
        )
        payload = report.model_dump()
        payload["one_pager_markdown"] = build_one_pager(
            report, company_name=intake.get("company_name")
        )
        response = JSONResponse(content=payload)
        response.headers["X-Assessment-Id"] = assessment_id
        return response
    except HTTPException:
        db.update_status(assessment_id, "failed", error="HTTPException")
        raise
    except Exception as exc:
        db.update_status(
            assessment_id, "failed", error=str(exc) or exc.__class__.__name__
        )
        raise _map_assessment_error(exc) from exc


@app.get("/assess/{unused}")
def assess_get_hint(unused: str):
    """Hint that assessment is POST-only."""
    return JSONResponse(
        status_code=405,
        content={
            "detail": (
                "Use POST /assess or POST /api/assessments/stream with JSON body "
                "{question, industry, company_size, company_name, role_title, "
                "primary_systems, constraints, success_metric, checklist}"
            )
        },
    )


@app.get("/r/{assessment_id}")
def share_report_page(assessment_id: str):
    """Serve shareable read-only report page."""
    row = db.get_by_id(assessment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return FileResponse(STATIC_DIR / "report.html")


@app.get("/")
def index():
    """Serve the single-page UI."""
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

__all__ = ["app", "to_markdown"]
