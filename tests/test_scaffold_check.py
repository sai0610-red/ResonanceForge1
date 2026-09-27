"""Tests for the static scaffold compile-check (no exec, no LLM calls)."""

from __future__ import annotations

from app.services.scaffold_check import check_scaffold, extract_python

VALID = '''from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class S(TypedDict):
    x: int


def step(state: S) -> S:
    """Increment."""
    return {"x": state["x"] + 1}


graph = StateGraph(S)
graph.add_node("step", step)
graph.add_edge(START, "step")
graph.add_edge("step", END)
app = graph.compile()
'''


def test_valid_code_passes():
    r = check_scaffold(VALID)
    assert r["ok"] is True
    assert r["error"] is None
    assert r["lines"] == len(VALID.strip().splitlines())
    assert r["has_stategraph"] is True
    assert r["has_compile"] is True


def test_syntax_error_fails_with_message():
    r = check_scaffold("def broken(:\n    return 1\n")
    assert r["ok"] is False
    assert r["error"] and "SyntaxError" in r["error"]
    assert r["lines"] == 2


def test_fenced_code_is_extracted():
    fenced = "Here is the code:\n```python\n" + VALID + "```\nDone."
    assert extract_python(fenced).startswith("from typing import TypedDict")
    r = check_scaffold(fenced)
    assert r["ok"] is True
    assert r["has_stategraph"] and r["has_compile"]


def test_bare_fence_without_language():
    r = check_scaffold("```\nx = 1\n```")
    assert r["ok"] is True
    assert r["lines"] == 1


def test_empty_input_is_not_ok_and_does_not_raise():
    for value in ("", "   \n", None, "```python\n```"):
        r = check_scaffold(value)
        assert r["ok"] is False
        assert r["lines"] == 0
        assert r["error"]


def test_flags_absent():
    r = check_scaffold("print('hello')\n")
    assert r["ok"] is True
    assert r["has_stategraph"] is False
    assert r["has_compile"] is False


def test_compile_flag_requires_method_call():
    r = check_scaffold("from langgraph.graph import StateGraph\ncompile_me = 1\n")
    assert r["has_stategraph"] is True
    assert r["has_compile"] is False


def test_code_is_never_executed(tmp_path):
    marker = tmp_path / "executed.txt"
    code = f"open({str(marker)!r}, 'w').write('x')\n"
    r = check_scaffold(code)
    assert r["ok"] is True
    assert not marker.exists()


def test_null_bytes_do_not_raise():
    r = check_scaffold("x = 1\x00\n")
    assert r["ok"] is False
    assert r["error"]
