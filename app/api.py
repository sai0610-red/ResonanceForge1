"""FastAPI application for ResonanceForge."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.graphs.resonance_graph import run_assessment
from app.models.schemas import AssessRequest, ResonanceReport
from app.services.report import to_markdown

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

app = FastAPI(
    title="ResonanceForge",
    description="Multi-agent AI readiness assessment platform",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    """Serve the single-page UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/assess", response_model=ResonanceReport)
def assess(body: AssessRequest):
    """Run the four-agent ResonanceForge assessment."""
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")

    try:
        from app.core.config import get_settings

        get_settings()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "GROQ_API_KEY is missing or invalid. "
                "Copy .env.example to .env and set GROQ_API_KEY. "
                f"({exc})"
            ),
        ) from exc

    try:
        report = run_assessment(
            question=question,
            industry=body.industry,
            company_size=body.company_size,
        )
        return report
    except HTTPException:
        raise
    except Exception as exc:
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
            raise HTTPException(
                status_code=502,
                detail=f"LLM provider error: {message}",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Assessment failed: {message}",
        ) from exc


@app.get("/assess/{unused}")
def assess_get_hint(unused: str):
    """Hint that assessment is POST-only."""
    return JSONResponse(
        status_code=405,
        content={"detail": "Use POST /assess with JSON body {question, industry, company_size}"},
    )


# Expose markdown helper for potential future download endpoint use
__all__ = ["app", "to_markdown"]
