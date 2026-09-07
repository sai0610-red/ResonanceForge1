"""Architect agent — multi-agent system design."""

from app.core.llm import get_llm
from app.models.schemas import ArchitectureResult, DiagnosisResult

SYSTEM_PROMPT = """You are a senior multi-agent systems architect specializing in LangGraph-based designs.

Given a company situation and readiness diagnosis, design a practical multi-agent architecture.

Rules:
- recommended_agents: list of named agent roles with clear responsibilities (typically 3–6 agents).
- high_level_flow: ordered steps describing how agents collaborate (START → … → END style narrative steps).
- rationale: explain why this design fits the company readiness and industry.
- estimated_complexity: Low / Medium / High based on integration depth, number of agents, and risk.
Favor pragmatic pilot-ready designs over enterprise mega-systems when readiness is Low or Medium.
"""


def run_architect(
    question: str,
    diagnosis: DiagnosisResult,
    industry: str | None = None,
    company_size: str | None = None,
) -> ArchitectureResult:
    """Design a multi-agent architecture informed by the diagnosis."""
    llm = get_llm().with_structured_output(ArchitectureResult)

    context_parts = [
        f"Company situation / question:\n{question}",
        f"Diagnosis JSON:\n{diagnosis.model_dump_json(indent=2)}",
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
