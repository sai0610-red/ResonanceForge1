"""LangGraph orchestration: diagnostician → architect → code_generator → critic."""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.architect import run_architect
from app.agents.code_generator import run_code_generator
from app.agents.critic import run_critic
from app.agents.diagnostician import run_diagnostician
from app.models.schemas import (
    ArchitectureResult,
    CodeGenerationResult,
    CritiqueResult,
    DiagnosisResult,
    ResonanceReport,
)
from app.services.context import gap_summary_from_diagnosis

INTAKE_KEYS = (
    "industry",
    "company_size",
    "company_name",
    "role_title",
    "primary_systems",
    "constraints",
    "success_metric",
)


def _replace(_old, new):
    """Reducer that replaces the previous value."""
    return new


class ResonanceState(TypedDict, total=False):
    question: Annotated[str, _replace]
    industry: Annotated[Optional[str], _replace]
    company_size: Annotated[Optional[str], _replace]
    company_name: Annotated[Optional[str], _replace]
    role_title: Annotated[Optional[str], _replace]
    primary_systems: Annotated[Optional[str], _replace]
    constraints: Annotated[Optional[str], _replace]
    success_metric: Annotated[Optional[str], _replace]
    checklist: Annotated[Optional[Any], _replace]
    diagnosis: Annotated[Optional[DiagnosisResult], _replace]
    architecture: Annotated[Optional[ArchitectureResult], _replace]
    generated_code: Annotated[Optional[CodeGenerationResult], _replace]
    critique: Annotated[Optional[CritiqueResult], _replace]


def _intake_kwargs(state: ResonanceState) -> dict:
    return {k: state.get(k) for k in INTAKE_KEYS}


def _diagnostician_node(state: ResonanceState) -> dict:
    result = run_diagnostician(
        question=state["question"],
        checklist=state.get("checklist"),
        **_intake_kwargs(state),
    )
    return {"diagnosis": result}


def _architect_node(state: ResonanceState) -> dict:
    diagnosis = state["diagnosis"]
    gap_summary = gap_summary_from_diagnosis(diagnosis) if diagnosis else None
    result = run_architect(
        question=state["question"],
        diagnosis=diagnosis,
        checklist_gap_summary=gap_summary,
        **_intake_kwargs(state),
    )
    return {"architecture": result}


def _code_generator_node(state: ResonanceState) -> dict:
    diagnosis = state["diagnosis"]
    gap_summary = gap_summary_from_diagnosis(diagnosis) if diagnosis else None
    result = run_code_generator(
        question=state["question"],
        diagnosis=diagnosis,
        architecture=state["architecture"],
        checklist_gap_summary=gap_summary,
        **_intake_kwargs(state),
    )
    return {"generated_code": result}


def _critic_node(state: ResonanceState) -> dict:
    diagnosis = state["diagnosis"]
    gap_summary = gap_summary_from_diagnosis(diagnosis) if diagnosis else None
    result = run_critic(
        question=state["question"],
        diagnosis=diagnosis,
        architecture=state["architecture"],
        generated_code=state["generated_code"],
        checklist_gap_summary=gap_summary,
        **_intake_kwargs(state),
    )
    return {"critique": result}


def build_graph():
    """Compile the ResonanceForge assessment graph."""
    graph = StateGraph(ResonanceState)
    graph.add_node("diagnostician", _diagnostician_node)
    graph.add_node("architect", _architect_node)
    graph.add_node("code_generator", _code_generator_node)
    graph.add_node("critic", _critic_node)

    graph.add_edge(START, "diagnostician")
    graph.add_edge("diagnostician", "architect")
    graph.add_edge("architect", "code_generator")
    graph.add_edge("code_generator", "critic")
    graph.add_edge("critic", END)

    return graph.compile()


_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def run_assessment(
    question: str,
    industry: str | None = None,
    company_size: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    primary_systems: str | None = None,
    constraints: str | None = None,
    success_metric: str | None = None,
    checklist: List[Any] | Dict[str, int] | None = None,
) -> ResonanceReport:
    """Run the full four-agent assessment and return a ResonanceReport."""
    if not question or not question.strip():
        raise ValueError("question must be a non-empty string")

    graph = get_compiled_graph()
    final: ResonanceState = graph.invoke(
        {
            "question": question.strip(),
            "industry": industry,
            "company_size": company_size,
            "company_name": company_name,
            "role_title": role_title,
            "primary_systems": primary_systems,
            "constraints": constraints,
            "success_metric": success_metric,
            "checklist": checklist,
            "diagnosis": None,
            "architecture": None,
            "generated_code": None,
            "critique": None,
        }
    )

    return ResonanceReport(
        user_question=final["question"],
        diagnosis=final["diagnosis"],
        architecture=final["architecture"],
        generated_code=final["generated_code"],
        critique=final["critique"],
    )


def run_assessment_sequential(
    question: str,
    industry: str | None = None,
    company_size: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    primary_systems: str | None = None,
    constraints: str | None = None,
    success_metric: str | None = None,
    checklist: List[Any] | Dict[str, int] | None = None,
    on_step=None,
) -> ResonanceReport:
    """
    Run agents in order (same outputs as the LangGraph path).

    on_step(step, name, label, partial) is called when a step starts (partial=None)
    and again after it finishes with partial payload.
    """
    if not question or not question.strip():
        raise ValueError("question must be a non-empty string")

    q = question.strip()
    intake = dict(
        industry=industry,
        company_size=company_size,
        company_name=company_name,
        role_title=role_title,
        primary_systems=primary_systems,
        constraints=constraints,
        success_metric=success_metric,
    )

    if on_step:
        on_step(1, "diagnostician", "Diagnosing readiness", None)
    diagnosis = run_diagnostician(question=q, checklist=checklist, **intake)
    gap_summary = gap_summary_from_diagnosis(diagnosis)
    if on_step:
        on_step(
            1,
            "diagnostician",
            "Diagnosing readiness",
            {"diagnosis": diagnosis.model_dump()},
        )

    if on_step:
        on_step(2, "architect", "Designing architecture", None)
    architecture = run_architect(
        question=q,
        diagnosis=diagnosis,
        checklist_gap_summary=gap_summary,
        **intake,
    )
    if on_step:
        on_step(
            2,
            "architect",
            "Designing architecture",
            {"architecture": architecture.model_dump()},
        )

    if on_step:
        on_step(3, "code_generator", "Generating LangGraph code", None)
    generated_code = run_code_generator(
        question=q,
        diagnosis=diagnosis,
        architecture=architecture,
        checklist_gap_summary=gap_summary,
        **intake,
    )
    if on_step:
        on_step(
            3,
            "code_generator",
            "Generating LangGraph code",
            {
                "generated_code": {
                    "language": generated_code.language,
                    "framework": generated_code.framework,
                    "explanation": generated_code.explanation,
                }
            },
        )

    if on_step:
        on_step(4, "critic", "Critiquing solution", None)
    critique = run_critic(
        question=q,
        diagnosis=diagnosis,
        architecture=architecture,
        generated_code=generated_code,
        checklist_gap_summary=gap_summary,
        **intake,
    )
    if on_step:
        on_step(
            4,
            "critic",
            "Critiquing solution",
            {"critique": critique.model_dump()},
        )

    return ResonanceReport(
        user_question=q,
        diagnosis=diagnosis,
        architecture=architecture,
        generated_code=generated_code,
        critique=critique,
    )
