"""Static compile-check for generated LangGraph scaffolds.

Parses and byte-compiles the generated Python WITHOUT executing it.
Never raises: any failure is reported as ok=False with an error string.
"""

from __future__ import annotations

import ast
import re
import warnings
from typing import Any, Dict, Optional

_FENCE_BLOCK = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_COMPILE_CALL = re.compile(r"\.compile\s*\(")


def extract_python(code: Optional[str]) -> str:
    """Return raw Python source, stripping markdown code fences if present."""
    text = (code or "").strip()
    if "```" not in text:
        return text
    match = _FENCE_BLOCK.search(text)
    if match:
        return match.group(1).strip()
    # Unbalanced fence (e.g. opening fence only): drop fence lines.
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
    return "\n".join(lines).strip()


def check_scaffold(code: Optional[str]) -> Dict[str, Any]:
    """Return {ok, error, lines, has_stategraph, has_compile}; never raises."""
    result: Dict[str, Any] = {
        "ok": False,
        "error": None,
        "lines": 0,
        "has_stategraph": False,
        "has_compile": False,
    }
    try:
        source = extract_python(code)
        result["lines"] = len(source.splitlines())
        result["has_stategraph"] = "StateGraph" in source
        result["has_compile"] = bool(_COMPILE_CALL.search(source))
        if not source:
            result["error"] = "No code to check (empty input)."
            return result
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ast.parse(source, filename="<generated>")
            compile(source, "<generated>", "exec", dont_inherit=True)
        result["ok"] = True
    except SyntaxError as exc:
        where = f"line {exc.lineno}" if exc.lineno else "unknown line"
        result["error"] = f"SyntaxError at {where}: {exc.msg}"
    except Exception as exc:  # RecursionError, MemoryError, ValueError (null bytes), ...
        result["error"] = f"{exc.__class__.__name__}: {exc}"[:500]
    return result
