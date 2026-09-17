"""Critic agent — reviews diagnosis, architecture, and generated code."""

from app.core.llm import get_llm
from app.models.schemas import (
    ArchitectureResult,
    CodeGenerationResult,
    CritiqueResult,
    DiagnosisResult,
)
from app.services.context import format_intake_context

SYSTEM_PROMPT = """You are a rigorous AI solutions critic and risk reviewer for enterprise multi-agent pilots.

Review the diagnosis, architecture, and generated LangGraph code for realism, safety, and pilot readiness.

Rules:
- strengths: what is solid and worth keeping.
- weaknesses: gaps, over-optimism, missing controls, weak code assumptions.
- risks: operational, security, data, compliance, or change-management risks.
- recommendations: concrete next steps (3+ items preferred).
- final_verdict: exactly one of "Ready for pilot", "Needs work", "Not ready".
Be candid. Do not rubber-stamp Low-readiness situations as ready for pilot.

Weigh checklist gaps and primary systems heavily in risks and final_verdict.
"""


def run_critic(
    question: str,
    diagnosis: DiagnosisResult,
    architecture: ArchitectureResult,
    generated_code: CodeGenerationResult,
    industry: str | None = None,
    company_size: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    primary_systems: str | None = None,
    constraints: str | None = None,
    success_metric: str | None = None,
    checklist_gap_summary: str | None = None,
) -> CritiqueResult:
    """Critique the full assessment package."""
    llm = get_llm().with_structured_output(CritiqueResult)

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
        f"{context}\n\n"
        f"Diagnosis JSON:\n{diagnosis.model_dump_json(indent=2)}\n\n"
        f"Architecture JSON:\n{architecture.model_dump_json(indent=2)}\n\n"
        f"Generated code explanation:\n{generated_code.explanation}\n\n"
        f"Generated code:\n{generated_code.code}"
    )

    return llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
