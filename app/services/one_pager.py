"""Stakeholder 1-pager (leadership brief) from a ResonanceReport."""

from __future__ import annotations

from typing import Optional

from app.models.schemas import ResonanceReport


def _cost_band(complexity: str, overall: str) -> str:
    """Heuristic cost band from architecture complexity + readiness."""
    c = (complexity or "Medium").lower()
    o = (overall or "Medium").lower()
    if c == "high" or (c == "medium" and o == "low"):
        return "High"
    if c == "low" and o == "high":
        return "Low"
    if c == "low":
        return "Low"
    if c == "high":
        return "High"
    return "Medium"


def _ninety_day_plan(gaps: list[str]) -> list[str]:
    plan = [
        "Days 1–30: Close the top checklist gaps that block data access and ownership; name exec sponsor and pilot owner.",
        "Days 31–60: Stand up a narrow LangGraph pilot against 1–2 primary systems with HITL review and basic evals.",
        "Days 61–90: Harden observability, security review, and go/no-go against the success metric.",
    ]
    if gaps:
        plan.append(f"Priority gap focus: {gaps[0]}")
        if len(gaps) > 1:
            plan.append(f"Secondary focus: {gaps[1]}")
    return plan


def build_one_pager(
    report: ResonanceReport,
    *,
    company_name: Optional[str] = None,
) -> str:
    """Return markdown leadership brief sections."""
    d = report.diagnosis
    a = report.architecture
    c = report.critique
    title = company_name or "Organization"
    cost = _cost_band(a.estimated_complexity, d.overall_readiness)
    plan = _ninety_day_plan(list(d.top_gaps))

    lines: list[str] = []
    lines.append(f"# Leadership brief — {title}")
    lines.append("")
    lines.append("## Executive verdict")
    lines.append("")
    lines.append(
        f"**{c.final_verdict}** · Overall readiness **{d.overall_readiness}** · "
        f"Estimated complexity **{a.estimated_complexity}** · Cost band **{cost}**."
    )
    lines.append("")
    lines.append(d.summary)
    lines.append("")
    lines.append("## Scores")
    lines.append("")
    lines.append("| Dimension | Score | Driver |")
    lines.append("|-----------|------:|--------|")
    lines.append(f"| ACCESS | {d.access.score}/10 | {d.access.reason} |")
    lines.append(f"| ADAPT | {d.adapt.score}/10 | {d.adapt.reason} |")
    lines.append(f"| ADOPT | {d.adopt.score}/10 | {d.adopt.reason} |")
    lines.append("")
    lines.append("## Top gaps")
    lines.append("")
    for gap in d.top_gaps:
        lines.append(f"- {gap}")
    lines.append("")
    lines.append("## 90-day plan")
    lines.append("")
    for step in plan:
        lines.append(f"- {step}")
    lines.append("")
    lines.append("## Cost band")
    lines.append("")
    lines.append(
        f"**{cost}** — heuristic from architecture complexity "
        f"({a.estimated_complexity}) and readiness ({d.overall_readiness}). "
        "Refine with actual LLM spend, integration effort, and partner fees."
    )
    lines.append("")
    lines.append("## Go / No-Go")
    lines.append("")
    lines.append(f"**{c.final_verdict}**")
    if c.recommendations:
        lines.append("")
        lines.append("Immediate recommendations:")
        for rec in c.recommendations[:4]:
            lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def one_pager_sections(
    report: ResonanceReport,
    *,
    company_name: Optional[str] = None,
) -> dict:
    """Structured sections for UI rendering."""
    d = report.diagnosis
    a = report.architecture
    c = report.critique
    cost = _cost_band(a.estimated_complexity, d.overall_readiness)
    return {
        "title": company_name or "Organization",
        "executive_verdict": (
            f"{c.final_verdict} · Overall readiness {d.overall_readiness} · "
            f"Complexity {a.estimated_complexity} · Cost band {cost}"
        ),
        "summary": d.summary,
        "scores": {
            "access": d.access.score,
            "adapt": d.adapt.score,
            "adopt": d.adopt.score,
            "overall": d.overall_readiness,
            "access_reason": d.access.reason,
            "adapt_reason": d.adapt.reason,
            "adopt_reason": d.adopt.reason,
        },
        "top_gaps": list(d.top_gaps),
        "ninety_day_plan": _ninety_day_plan(list(d.top_gaps)),
        "cost_band": cost,
        "go_no_go": c.final_verdict,
        "recommendations": list(c.recommendations[:4]),
        "markdown": build_one_pager(report, company_name=company_name),
    }
