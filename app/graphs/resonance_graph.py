"""LangGraph orchestration: diagnostician → architect → code_generator → critic."""

from typing import Annotated, Optional, TypedDict

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


def _replace(_old, new):
    """Reducer that replaces the previous value."""
    return new


class ResonanceState(TypedDict, total=False):
    question: Annotated[str, _replace]
    industry: Annotated[Optional[str], _replace]
    company_size: Annotated[Optional[str], _replace]
    diagnosis: Annotated[Optional[DiagnosisResult], _replace]
    architecture: Annotated[Optional[ArchitectureResult], _replace]
    generated_code: Annotated[Optional[CodeGenerationResult], _replace]
    critique: Annotated[Optional[CritiqueResult], _replace]


def _diagnostician_node(state: ResonanceState) -> dict:
    result = run_diagnostician(
        question=state["question"],
        industry=state.get("industry"),
        company_size=state.get("company_size"),
    )
    return {"diagnosis": result}


def _architect_node(state: ResonanceState) -> dict:
    result = run_architect(
        question=state["question"],
        diagnosis=state["diagnosis"],
        industry=state.get("industry"),
        company_size=state.get("company_size"),
    )
    return {"architecture": result}


def _code_generator_node(state: ResonanceState) -> dict:
    result = run_code_generator(
        question=state["question"],
        diagnosis=state["diagnosis"],
        architecture=state["architecture"],
        industry=state.get("industry"),
        company_size=state.get("company_size"),
    )
    return {"generated_code": result}


def _critic_node(state: ResonanceState) -> dict:
    result = run_critic(
        question=state["question"],
        diagnosis=state["diagnosis"],
        architecture=state["architecture"],
        generated_code=state["generated_code"],
        industry=state.get("industry"),
        company_size=state.get("company_size"),
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
