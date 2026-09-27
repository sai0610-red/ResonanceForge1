"""Architect agent — multi-agent system design."""

from app.core.llm import get_llm
from app.models.schemas import ArchitectureResult, DiagnosisResult
from app.services.context import format_intake_context

SYSTEM_PROMPT = """You are a senior multi-agent systems architect specializing in LangGraph-based designs.

Given a company situation and readiness diagnosis, design a practical multi-agent architecture.

Rules:
- recommended_agents: list of named agent roles with clear responsibilities (typically 3–6 agents).
- high_level_flow: ordered steps describing how agents collaborate (START → … → END style narrative steps).
- rationale: explain why this design fits the company readiness and industry.
- estimated_complexity: Low / Medium / High based on integration depth, number of agents, and risk.
Favor pragmatic pilot-ready designs over enterprise mega-systems when readiness is Low or Medium.

Map architecture to the checklist gaps and named primary systems when provided.
"""


def run_architect(
    question: str,
    diagnosis: DiagnosisResult,
    industry: str | None = None,
    company_size: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    primary_systems: str | None = None,
    constraints: str | None = None,
    success_metric: str | None = None,
    checklist_gap_summary: str | None = None,
) -> ArchitectureResult:
    """Design a multi-agent architecture informed by the diagnosis."""
    llm = get_llm().with_structured_output(ArchitectureResult)

    context = format_intake_context(
        question=question,
        industry=industry,
        company_size=company_size,
        company_name=company_name,
        role_title=role_title,
        primary_systems=primary_systems,
        constraints=constraints,
        success_metric=success_metric,
        checklist_gap_summary=checklist_gap_summary,
    )
    user_prompt = (
        f"{context}\n\nDiagnosis JSON:\n{diagnosis.model_dump_json(indent=2)}"
    )

    return llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
