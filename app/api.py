"""FastAPI application for ResonanceForge."""

from __future__ import annotations

import contextvars
import hmac
import json
import logging
import queue
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Generator, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.agents.architect import run_architect
from app.agents.code_generator import run_code_generator
from app.agents.critic import run_critic
from app.agents.diagnostician import run_diagnostician
from app.core.agent_log import agent_timer, configure_logging, request_id_var
from app.core.config import get_settings
from app.core.llm import LLMUnavailable, wait_listener
from app.core.rate_limit import SlidingWindowRateLimiter, client_ip
from app.graphs.resonance_graph import run_assessment
from app.rag import service as rag
from app.models.schemas import AssessRequest, ResonanceReport, ScaffoldCheck
from app.rubric.checklist import get_checklist_payload
from app.services.context import gap_summary_from_diagnosis
from app.services.one_pager import build_one_pager, one_pager_sections
from app.services.pilot_package import attach_pilot, pilot_zip_path
from app.services.report import to_markdown
from app.services.scaffold_check import check_scaffold

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

logger = logging.getLogger("resonanceforge.api")

# Per-IP sliding window for assessment-creating endpoints (in-memory).
rate_limiter = SlidingWindowRateLimiter(window_seconds=3600)
# Separate, looser window for document uploads (no LLM cost, but CPU + disk).
upload_limiter = SlidingWindowRateLimiter(window_seconds=3600)

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    # Raises RuntimeError (app refuses to start) in production without secrets.
    settings.validate_for_startup()
    db.ensure_db()
    logger.info(
        "startup env=%s provider=%s model=%s demo_token_required=%s rate_limit_per_hour=%d "
        "trusted_proxy=%s data_dir=%s",
        settings.env,
        settings.provider,
        settings.active_model,
        bool(settings.demo_token),
        settings.rate_limit_per_hour,
        settings.trusted_proxy,
        settings.data_path,
    )
    yield


app = FastAPI(
    title="ResonanceForge",
    description="Multi-agent AI readiness assessment platform",
    version="1.3.0",
    lifespan=lifespan,
)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id and security headers to every response."""
    incoming = (request.headers.get("x-request-id") or "").strip()
    rid = incoming if _REQUEST_ID_RE.fullmatch(incoming) else str(uuid.uuid4())
    request.state.request_id = rid
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
    )
    if get_settings().is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


_cors_origins = get_settings().cors_origin_list
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Demo-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Assessment-Id", "Retry-After"],
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
    settings = get_settings()
    hop = "last" if (settings.trusted_proxy_hop or "").strip().lower() == "last" else "first"
    return client_ip(request, trusted_proxy=settings.trusted_proxy, hop=hop)


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


def _load_grounding(body: AssessRequest) -> rag.Grounding:
    """422 for an unknown document_set_id, before the assessment row or any LLM call."""
    try:
        return rag.load(body.document_set_id)
    except rag.DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


def _ensure_llm_configured() -> None:
    """500 before any work when the configured LLM provider cannot be called."""
    problem = get_settings().llm_config_error()
    if problem:
        raise HTTPException(status_code=500, detail=problem)


def _map_assessment_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMUnavailable):
        return HTTPException(status_code=502, detail=str(exc))
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
            "bedrock",
            "accessdenied",
            "credentials",
            "security token",
        )
    ):
        # Never echo provider error text — it can include credentials.
        hint = (
            "Check the task role / AWS credentials and Bedrock model access"
            if get_settings().provider == "bedrock"
            else "Check GROQ_API_KEY"
        )
        return HTTPException(
            status_code=502,
            detail=f"LLM provider error. {hint} and try again.",
        )
    return HTTPException(
        status_code=502,
        detail="Assessment failed. Please retry; if it persists, check the server logs.",
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
        "provider": settings.provider,
        "model": settings.active_model,
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
        "document_set_id": row.get("document_set_id"),
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


_SSE_KEEPALIVE_SECONDS = 15.0


def _run_agent_streaming(
    assessment_id: str, step: int, agent: str, fn, **kwargs
) -> Generator[str, None, Any]:
    """Run one agent in a worker thread; yield SSE status/keepalive while it runs.

    Use as `result = yield from _run_agent_streaming(...)`. When the LLM layer waits
    on a provider rate limit, a `status` event tells the UI instead of looking frozen.
    """
    events: "queue.Queue[str]" = queue.Queue()

    def on_wait(seconds: float, reason: str) -> None:
        events.put(
            _sse(
                "status",
                {
                    "step": step,
                    "name": agent,
                    "id": assessment_id,
                    "status": "waiting_rate_limit" if reason == "rate_limit" else reason,
                    "wait_seconds": round(seconds, 1),
                    "label": f"Waiting on model rate limit (~{round(seconds)}s)",
                },
            )
        )

    def target():
        with wait_listener(on_wait):
            return _run_agent(assessment_id, agent, fn, **kwargs)

    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(ctx.run, target)
        last_sent = time.monotonic()
        while True:
            try:
                yield events.get(timeout=0.25)
                last_sent = time.monotonic()
            except queue.Empty:
                if future.done():
                    break
                if time.monotonic() - last_sent >= _SSE_KEEPALIVE_SECONDS:
                    # SSE comment line: keeps proxies from closing an idle stream.
                    yield ": keepalive\n\n"
                    last_sent = time.monotonic()
        while not events.empty():
            yield events.get_nowait()
        return future.result()


@app.post("/api/assessments/stream", dependencies=[Depends(require_demo_token)])
def api_assess_stream(body: AssessRequest, request: Request):
    """Run assessment with SSE progress events; persist result + pilot zip."""
    question = _validated_question(body)
    _ensure_llm_configured()
    _enforce_rate_limit(request)
    intake = _intake_from_body(body)
    checklist = _checklist_from_body(body)
    grounding = _load_grounding(body)

    assessment_id = db.create_assessment(
        question=question,
        status="running",
        checklist=checklist,
        document_set_id=grounding.document_set_id,
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
            diagnosis = yield from _run_agent_streaming(
                assessment_id,
                1,
                "diagnostician",
                run_diagnostician,
                question=question,
                checklist=checklist,
                passages=(
                    rag.passages_block(rag.retrieve_for_diagnosis(grounding, question, intake))
                    if rag.needs_llm_diagnosis(checklist)
                    else None
                ),
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
            gap_summary = gap_summary_from_diagnosis(diagnosis)

            yield _sse(
                "step",
                {
                    "step": 2,
                    "name": "architect",
                    "label": "Designing architecture",
                    "id": assessment_id,
                },
            )
            architecture = yield from _run_agent_streaming(
                assessment_id,
                2,
                "architect",
                run_architect,
                question=question,
                diagnosis=diagnosis,
                checklist_gap_summary=gap_summary,
                passages=rag.passages_block(
                    rag.retrieve_for_architect(grounding, question, intake, diagnosis)
                ),
                **intake,
            )
            # Drop citations that do not point at a retrieved chunk before anything
            # downstream (UI, code generator, critic) sees the text.
            diagnosis, architecture, evidence = rag.ground(grounding, diagnosis, architecture)
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
            generated_code = yield from _run_agent_streaming(
                assessment_id,
                3,
                "code_generator",
                run_code_generator,
                question=question,
                diagnosis=diagnosis,
                architecture=architecture,
                checklist_gap_summary=gap_summary,
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
            critique = yield from _run_agent_streaming(
                assessment_id,
                4,
                "critic",
                run_critic,
                question=question,
                diagnosis=diagnosis,
                architecture=architecture,
                generated_code=generated_code,
                checklist_gap_summary=gap_summary,
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
                evidence=evidence,
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
            mapped = _map_assessment_error(exc)
            message = mapped.detail if isinstance(mapped.detail, str) else "Assessment failed"
            try:
                db.update_status(assessment_id, "failed", error=exc.__class__.__name__)
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
    _ensure_llm_configured()
    _enforce_rate_limit(request)
    intake = _intake_from_body(body)
    checklist = _checklist_from_body(body)
    grounding = _load_grounding(body)

    assessment_id = db.create_assessment(
        question=question,
        status="running",
        checklist=checklist,
        document_set_id=grounding.document_set_id,
        **intake,
    )

    try:
        report = run_assessment(
            question=question,
            checklist=checklist,
            assessment_id=assessment_id,
            grounding=grounding,
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


def _enforce_upload_rate_limit(request: Request) -> None:
    limit = get_settings().upload_rate_limit_per_hour
    allowed, retry_after = upload_limiter.check(_client_ip(request), limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Upload rate limit exceeded: {limit} per hour. Retry in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


@app.post("/api/documents", dependencies=[Depends(require_demo_token)])
async def api_upload_documents(request: Request, files: list[UploadFile] = File(...)):
    """Upload customer docs (txt / md / pdf) for grounding. Returns a document_set_id.

    Pass that id as `document_set_id` on POST /assess or /api/assessments/stream.
    Only extracted text and chunks are stored; the raw bytes are discarded.
    """
    _enforce_upload_rate_limit(request)
    settings = get_settings()
    if len(files) > settings.rag_max_files:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files ({len(files)}); maximum is {settings.rag_max_files}",
        )
    payload: list[tuple[str, bytes]] = []
    for upload in files:
        # Read one byte past the limit so an oversize file is rejected without
        # holding more than max+1 bytes per file in memory.
        data = await upload.read(settings.rag_max_file_bytes + 1)
        await upload.close()
        payload.append((upload.filename or "document", data))
    try:
        record = rag.ingest(payload)
    except rag.DocumentError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    logger.info(
        "documents_uploaded set_id=%s files=%d chunks=%d",
        record["id"],
        len(record["documents"]),
        sum(d["chunks"] for d in record["documents"]),
    )
    return {"document_set_id": record["id"], **record}


@app.get("/api/documents/{set_id}", dependencies=[Depends(require_demo_token)])
def api_get_documents(set_id: str):
    """Metadata for an uploaded set (labels, filenames, sizes, chunk counts)."""
    record = db.get_document_set(set_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document set not found")
    return {
        "document_set_id": record["id"],
        "created_at": record["created_at"],
        "documents": [
            {
                "label": d["label"],
                "filename": d["filename"],
                "char_count": d["char_count"],
                "chunks": len(d["chunks"]),
            }
            for d in record["documents"]
        ],
    }


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
