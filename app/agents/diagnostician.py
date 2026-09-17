"""Diagnostician agent — ACCESS / ADAPT / ADOPT readiness assessment."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.llm import get_llm
from app.models.schemas import DiagnosisResult
from app.rubric.checklist import (
    answers_from_checklist_list,
    is_checklist_complete,
    score_checklist,
)
from app.services.context import format_intake_context

SYSTEM_PROMPT = """You are an expert enterprise AI readiness diagnostician specializing in multi-agent systems.

Evaluate the company situation using the ACCESS / ADAPT / ADOPT framework:

- ACCESS (1–10): Data quality, infrastructure, tooling, and ability to reach the data/systems agents need.
- ADAPT (1–10): Organizational flexibility, process maturity, talent, and willingness to change workflows for AI agents.
- ADOPT (1–10): Leadership buy-in, budget, governance, change management, and realistic path to production adoption.

Rules:
- Scores must be integers from 1 to 10 with a clear reason for each.
- overall_readiness: "Low" if average < 4.5, "Medium" if average < 7.5, else "High".
- Provide 3–5 concrete top_gaps (specific, actionable).
- summary: 2–4 sentences synthesizing the readiness picture for multi-agent AI.
- When estimating without a complete checklist, prefix summary with
  "Estimated without checklist: " and note that reasons are estimated without checklist.
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
    checklist: List[Any] | Dict[str, int] | None = None,
) -> DiagnosisResult:
    """Diagnose multi-agent AI readiness; use rubric when checklist is complete."""
    if isinstance(checklist, dict):
        answers: Dict[str, int] = {str(k): int(v) for k, v in checklist.items()}
    else:
        answers = answers_from_checklist_list(checklist)

    if is_checklist_complete(answers):
        return score_checklist(answers)

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
        checklist_answers=answers or None,
    )
    user_prompt += (
        "\n\nNo complete 15-question checklist was provided. "
        "Estimate scores; prefix summary with 'Estimated without checklist: '; "
        "cite reasons as estimated without checklist."
    )

    result = llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    if not str(result.summary).startswith("Estimated without checklist"):
        result = result.model_copy(
            update={"summary": "Estimated without checklist: " + result.summary}
        )
    return result
