"""Critic agent — reviews diagnosis, architecture, and generated code."""

from app.core.llm import get_llm
from app.models.schemas import (
    ArchitectureResult,
    CodeGenerationResult,
    CritiqueResult,
    DiagnosisResult,
)

SYSTEM_PROMPT = """You are a rigorous AI solutions critic and risk reviewer for enterprise multi-agent pilots.

Review the diagnosis, architecture, and generated LangGraph code for realism, safety, and pilot readiness.

Rules:
- strengths: what is solid and worth keeping.
- weaknesses: gaps, over-optimism, missing controls, weak code assumptions.
- risks: operational, security, data, compliance, or change-management risks.
- recommendations: concrete next steps (3+ items preferred).
- final_verdict: exactly one of "Ready for pilot", "Needs work", "Not ready".
Be candid. Do not rubber-stamp Low-readiness situations as ready for pilot.
"""


def run_critic(
    question: str,
    diagnosis: DiagnosisResult,
    architecture: ArchitectureResult,
    generated_code: CodeGenerationResult,
    industry: str | None = None,
    company_size: str | None = None,
) -> CritiqueResult:
    """Critique the full assessment package."""
    llm = get_llm().with_structured_output(CritiqueResult)

    context_parts = [
        f"Company situation / question:\n{question}",
        f"Diagnosis JSON:\n{diagnosis.model_dump_json(indent=2)}",
        f"Architecture JSON:\n{architecture.model_dump_json(indent=2)}",
        f"Generated code explanation:\n{generated_code.explanation}",
        f"Generated code:\n{generated_code.code}",
    ]
    if industry:
        context_parts.append(f"Industry: {industry}")
    if company_size:
        context_parts.append(f"Company size: {company_size}")
    user_prompt = "\n\n".join(context_parts)

    return llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
