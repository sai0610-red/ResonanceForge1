"""Build a runnable Docker pilot zip for an assessment."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import List, Optional

from app.core.config import get_settings
from app.models.schemas import (
    ArchitectureResult,
    CodeGenerationResult,
    CritiqueResult,
    DiagnosisResult,
    PilotPackageInfo,
    ResonanceReport,
)



def get_pilots_dir() -> Path:
    """Pilot zips live under DATA_DIR/pilots."""
    return get_settings().data_path / "pilots"

_REQUIREMENTS = """langgraph>=0.2.0
langchain-core>=0.3.0
typing-extensions>=4.8.0
"""

_DOCKERFILE = """FROM python:3.12-slim
WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app/ /app/
CMD ["python", "main.py"]
"""

_COMPOSE = """services:
  pilot:
    build: .
    volumes:
      - ./app:/app
    environment:
      - PYTHONUNBUFFERED=1
"""


def _looks_like_valid_langgraph(code: str) -> bool:
    if not code or len(code.strip()) < 80:
        return False
    needed = ("StateGraph", "START", "END", "compile")
    return all(tok in code for tok in needed)


def _strip_markdown_fences(code: str) -> str:
    text = code.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:python)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text, count=1)
    return text.strip() + "\n"


def _stub_langgraph(architecture: ArchitectureResult, systems: Optional[str]) -> str:
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
        for a in agents[:6]:
            safe = re.sub(r"[^a-zA-Z0-9_]+", "_", a.name.strip().lower()).strip("_") or "agent"
            if safe[0].isdigit():
                safe = "agent_" + safe
            names.append(safe)
            responsibilities.append(a.responsibility)

    systems_note = systems or "primary enterprise systems"
    node_fns = []
    for name, resp in zip(names, responsibilities):
        node_fns.append(
            f'''
def {name}_node(state: PilotState) -> PilotState:
    """{resp}"""
    notes = list(state.get("notes") or [])
    notes.append("{name}: {resp}")
    return {{
        "request": state.get("request", ""),
        "notes": notes,
        "systems": state.get("systems") or "{systems_note}",
        "status": "{name}_done",
    }}
'''
        )

    edges = []
    edges.append(f'graph.add_edge(START, "{names[0]}")')
    for i in range(len(names) - 1):
        edges.append(f'graph.add_edge("{names[i]}", "{names[i+1]}")')
    edges.append(f'graph.add_edge("{names[-1]}", END)')

    add_nodes = "\n".join(
        f'graph.add_node("{n}", {n}_node)' for n in names
    )
    add_edges = "\n".join(edges)

    return f'''"""ResonanceForge pilot — LangGraph stub customized from architecture."""

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
{chr(10).join("    " + line for line in add_nodes.splitlines())}
{chr(10).join("    " + line for line in add_edges.splitlines())}
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


def _readme(assessment_id: str) -> str:
    return f"""# ResonanceForge runnable pilot

Assessment id: `{assessment_id}`

## Run with Docker

```bash
docker compose up --build
```

## Run locally

```bash
cd app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Tests

```bash
cd app
pip install -r requirements.txt
python -m pytest ../evals/test_pilot.py -q
# or: python ../evals/test_pilot.py
```

## Notes

- This package is a **starter pilot**, not production software.
- Review `WHAT_BREAKS_FIRST.md` before connecting real systems.
- Wire API keys and network access only after security review.
"""


def _what_breaks_first(
    diagnosis: DiagnosisResult,
    critique: CritiqueResult,
) -> List[str]:
    items: List[str] = []
    for gap in diagnosis.top_gaps[:4]:
        items.append(f"Checklist gap: {gap}")
    for risk in (critique.risks or [])[:3]:
        items.append(f"Critique risk: {risk}")
    for weak in (critique.weaknesses or [])[:2]:
        items.append(f"Weakness: {weak}")
    # de-dupe preserving order
    seen = set()
    out: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out[:8] or [
        "Unclear ownership and missing HITL will break first under real traffic.",
        "Stale or incomplete data feeds will cause silent wrong actions.",
        "Missing evals will hide quality regressions until users complain.",
    ]


def _evals_test() -> str:
    return '''"""Pilot smoke checks — graph compiles and invokes with sample state."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Allow importing main.py from sibling app/
APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))


class PilotSmokeTests(unittest.TestCase):
    def test_graph_compiles(self):
        # What breaks first: import errors / missing langgraph
        import main as pilot

        self.assertTrue(hasattr(pilot, "build_graph") or hasattr(pilot, "app"))
        graph = pilot.build_graph() if hasattr(pilot, "build_graph") else pilot.app
        self.assertIsNotNone(graph)

    def test_invoke_sample_state(self):
        # What breaks first: TypedDict mismatch / node return shape
        import main as pilot

        graph = pilot.build_graph() if hasattr(pilot, "build_graph") else pilot.app
        result = graph.invoke(
            {
                "request": "smoke test",
                "notes": [],
                "systems": "erp,crm",
                "status": "start",
            }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("request", result)

    def test_has_langgraph_imports(self):
        # What breaks first: generated code without StateGraph
        src = (APP_DIR / "main.py").read_text(encoding="utf-8")
        self.assertIn("StateGraph", src)
        self.assertIn("START", src)
        self.assertIn("END", src)

    def test_nodes_are_callable(self):
        # What breaks first: missing node functions after rename
        import main as pilot
        import inspect

        callables = [
            name
            for name, obj in inspect.getmembers(pilot)
            if callable(obj) and name.endswith("_node")
        ]
        self.assertGreaterEqual(len(callables), 1)

    def test_readme_adjacent(self):
        # Packaging sanity
        root = Path(__file__).resolve().parent.parent
        self.assertTrue((root / "README.md").exists())
        self.assertTrue((root / "docker-compose.yml").exists())


if __name__ == "__main__":
    unittest.main()
'''


def build_pilot_package(
    assessment_id: str,
    report: ResonanceReport,
    *,
    primary_systems: Optional[str] = None,
) -> PilotPackageInfo:
    """
    Write DATA_DIR/pilots/{assessment_id}.zip and return PilotPackageInfo.
    Prefers generated_code.code when it looks like valid LangGraph; else stub.
    """
    pilots_dir = get_pilots_dir()
    pilots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{assessment_id}.zip"
    zip_path = pilots_dir / filename

    code = _strip_markdown_fences(report.generated_code.code or "")
    if _looks_like_valid_langgraph(code):
        main_py = code
        if "if __name__" not in main_py:
            main_py += (
                "\n\nif __name__ == '__main__':\n"
                "    g = build_graph() if 'build_graph' in dir() else app\n"
                "    print(g.invoke({'request': 'pilot demo', 'notes': [], "
                "'systems': 'demo', 'status': 'start'}))\n"
            )
    else:
        main_py = _stub_langgraph(report.architecture, primary_systems)

    breaks = _what_breaks_first(report.diagnosis, report.critique)
    breaks_md = "# What breaks first\n\n" + "\n".join(f"- {b}" for b in breaks) + "\n"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", _readme(assessment_id))
        zf.writestr("docker-compose.yml", _COMPOSE)
        zf.writestr("Dockerfile", _DOCKERFILE)
        zf.writestr("app/main.py", main_py)
        zf.writestr("app/requirements.txt", _REQUIREMENTS)
        zf.writestr("evals/test_pilot.py", _evals_test())
        zf.writestr("WHAT_BREAKS_FIRST.md", breaks_md)

    return PilotPackageInfo(
        download_path=f"/api/assessments/{assessment_id}/pilot.zip",
        filename=filename,
        what_breaks_first=breaks,
    )


def pilot_zip_path(assessment_id: str) -> Path:
    return get_pilots_dir() / f"{assessment_id}.zip"


def attach_pilot(
    assessment_id: str,
    report: ResonanceReport,
    *,
    primary_systems: Optional[str] = None,
) -> ResonanceReport:
    """Build zip and return report copy with pilot field set."""
    info = build_pilot_package(
        assessment_id, report, primary_systems=primary_systems
    )
    return report.model_copy(update={"pilot": info})
