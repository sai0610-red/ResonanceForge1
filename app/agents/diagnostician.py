"""Diagnostician agent — ACCESS / ADAPT / ADOPT readiness assessment."""

from app.core.llm import get_llm
from app.models.schemas import DiagnosisResult
from app.services.context import format_intake_context

SYSTEM_PROMPT = """You are an expert enterprise AI readiness diagnostician specializing in multi-agent systems.

Evaluate the company situation using the ACCESS / ADAPT / ADOPT framework:

- ACCESS (1–10): Data quality, infrastructure, tooling, and ability to reach the data/systems agents need.
- ADAPT (1–10): Organizational flexibility, process maturity, talent, and willingness to change workflows for AI agents.
- ADOPT (1–10): Leadership buy-in, budget, governance, change management, and realistic path to production adoption.

Rules:
- Scores must be integers from 1 to 10 with a clear reason for each.
- overall_readiness: "Low" if average < 4, "Medium" if average < 7, else "High".
- Provide 3–5 concrete top_gaps (specific, actionable).
- summary: 2–4 sentences synthesizing the readiness picture for multi-agent AI.
Be honest and specific; avoid generic fluff.
"""


def run_diagnostician(
    question: str,
    industry: str | None = None,
    company_size: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    primary_systems: str | None = None,
    constraints: str | None = None,
    success_metric: str | None = None,
) -> DiagnosisResult:
    """Diagnose multi-agent AI readiness for the given company situation."""
    llm = get_llm().with_structured_output(DiagnosisResult)

    user_prompt = format_intake_context(
        question=question,
        industry=industry,
        company_size=company_size,
        company_name=company_name,
        role_title=role_title,
        primary_systems=primary_systems,
        constraints=constraints,
        success_metric=success_metric,
    )

    return llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
