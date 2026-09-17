"""Code generator agent — produces valid LangGraph Python scaffolding."""

from __future__ import annotations

import logging
import re

from app.core.llm import get_llm
from app.models.schemas import ArchitectureResult, CodeGenerationResult, DiagnosisResult
from app.services.context import format_intake_context

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert LangGraph engineer. Generate complete, runnable Python code for a multi-agent workflow.

HARD REQUIREMENTS for the `code` field:
1. Must be valid Python using LangGraph.
2. MUST include these imports exactly (plus any others needed):
   from typing import TypedDict
   from langgraph.graph import StateGraph, START, END
3. Define a TypedDict for graph state.
4. Define real node functions (each with a docstring; return an updated state dict).
5. Build the graph with StateGraph, add_node, add_edge, connect START and END, and call compile().
6. Include `if __name__ == "__main__":` that invokes the compiled graph with sample input.
7. language must be "python"; framework must be "langgraph".

Keep the code compact (under 120 lines). Prefer simple string-returning stubs over complex LLM calls.
explanation: briefly describe how the code maps to the recommended architecture.
Do not wrap code in markdown fences — return raw Python source in the `code` field.
"""


def _safe_name(name: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", (name or "").strip().lower()).strip("_")
    if not s:
        s = fallback
    if s[0].isdigit():
        s = "agent_" + s
    return s


def _fallback_code(architecture: ArchitectureResult, systems: str | None) -> str:
    agents = architecture.recommended_agents or []
    if not agents:
        names = ["intake", "planner", "executor", "reviewer"]
        responsibilities = [
            "Normalize request",
            "Plan steps",
            "Call systems",
            "Human-in-the-loop check",
        ]
    else:
        names = []
        responsibilities = []
        for i, a in enumerate(agents[:6]):
            names.append(_safe_name(a.name, f"agent_{i}"))
            responsibilities.append(a.responsibility)

    systems_note = systems or "primary enterprise systems"
    node_fns = []
    for name, resp in zip(names, responsibilities):
        resp_safe = resp.replace('"', "'")
        node_fns.append(
            f'''
def {name}_node(state: PilotState) -> PilotState:
    """{resp_safe}"""
    notes = list(state.get("notes") or [])
    notes.append("{name}: {resp_safe}")
    return {{
        "request": state.get("request", ""),
        "notes": notes,
        "systems": state.get("systems") or "{systems_note}",
        "status": "{name}_done",
    }}
'''
        )

    add_nodes = "\n".join(f'    graph.add_node("{n}", {n}_node)' for n in names)
    edges = [f'    graph.add_edge(START, "{names[0]}")']
    for i in range(len(names) - 1):
        edges.append(f'    graph.add_edge("{names[i]}", "{names[i+1]}")')
    edges.append(f'    graph.add_edge("{names[-1]}", END)')
    add_edges = "\n".join(edges)

    return f'''"""ResonanceForge pilot — LangGraph scaffold from architecture."""

from __future__ import annotations

from typing import List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph


class PilotState(TypedDict, total=False):
    request: str
    notes: List[str]
    systems: Optional[str]
    status: str

{"".join(node_fns)}

def build_graph():
    graph = StateGraph(PilotState)
{add_nodes}
{add_edges}
    return graph.compile()


app = build_graph()


if __name__ == "__main__":
    result = app.invoke(
        {{
            "request": "Run pilot readiness check",
            "notes": [],
            "systems": "{systems_note}",
            "status": "start",
        }}
    )
    print("Pilot invoke OK")
    print(result)
'''


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
    checklist_gap_summary: str | None = None,
) -> CodeGenerationResult:
    """Generate LangGraph code from the architecture design (with stub fallback)."""
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
        "Generate compact LangGraph Python code implementing this architecture."
    )

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            llm = get_llm().with_structured_output(CodeGenerationResult)
            result = llm.invoke(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            if result and result.code and "StateGraph" in result.code:
                return result
        except Exception as exc:
            last_err = exc
            logger.warning("code_generator attempt %s failed: %s", attempt + 1, exc)

    logger.warning(
        "code_generator falling back to architecture stub (%s)", last_err
    )
    return CodeGenerationResult(
        language="python",
        framework="langgraph",
        code=_fallback_code(architecture, primary_systems),
        explanation=(
            "Fallback LangGraph scaffold generated from recommended agents "
            "(LLM structured output failed or returned invalid code). "
            "Customize node bodies and wire real system connectors before production."
        ),
    )
