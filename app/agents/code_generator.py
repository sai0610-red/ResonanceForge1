"""Code generator agent — produces valid LangGraph Python scaffolding."""

from app.core.llm import get_llm
from app.models.schemas import ArchitectureResult, CodeGenerationResult, DiagnosisResult
from app.services.context import format_intake_context

SYSTEM_PROMPT = """You are an expert LangGraph engineer. Generate complete, runnable Python code for a multi-agent workflow.

HARD REQUIREMENTS for the `code` field:
1. Must be valid Python using LangGraph.
2. MUST include these imports exactly (plus any others needed):
   from typing import TypedDict
   from langgraph.graph import StateGraph, START, END
3. Define a TypedDict for graph state.
4. Define real node functions (no fake/placeholder classes, no `pass` stubs that do nothing useful — each node should have a clear docstring and return an updated state dict).
5. Build the graph with StateGraph, add_node, add_edge (or add_conditional_edges if needed), connect START and END, and call compile().
6. Include a simple `if __name__ == "__main__":` demo that invokes the compiled graph with sample input.
7. language must be "python"; framework must be "langgraph".

explanation: briefly describe how the code maps to the recommended architecture.
Do not wrap code in markdown fences — return raw Python source in the `code` field.
"""


def run_code_generator(
    question: str,
    diagnosis: DiagnosisResult,
    architecture: ArchitectureResult,
    industry: str | None = None,
    company_size: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    primary_systems: str | None = None,
    constraints: str | None = None,
    success_metric: str | None = None,
) -> CodeGenerationResult:
    """Generate LangGraph code from the architecture design."""
    llm = get_llm().with_structured_output(CodeGenerationResult)

    context = format_intake_context(
        question=question,
        industry=industry,
        company_size=company_size,
        company_name=company_name,
        role_title=role_title,
        primary_systems=primary_systems,
        constraints=constraints,
        success_metric=success_metric,
    )
    user_prompt = (
        f"{context}\n\n"
        f"Diagnosis JSON:\n{diagnosis.model_dump_json(indent=2)}\n\n"
        f"Architecture JSON:\n{architecture.model_dump_json(indent=2)}\n\n"
        "Generate complete LangGraph Python code implementing this architecture."
    )

    return llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
