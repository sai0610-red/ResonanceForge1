"""Shared user-context formatting for agent prompts."""

from __future__ import annotations

from typing import Dict, Optional

from app.models.schemas import DiagnosisResult


def format_intake_context(
    *,
    question: str,
    industry: Optional[str] = None,
    company_size: Optional[str] = None,
    company_name: Optional[str] = None,
    role_title: Optional[str] = None,
    primary_systems: Optional[str] = None,
    constraints: Optional[str] = None,
    success_metric: Optional[str] = None,
    checklist_answers: Optional[Dict[str, int]] = None,
    checklist_gap_summary: Optional[str] = None,
) -> str:
    """Build the user-context block appended to agent prompts."""
    parts = [f"Company situation / question:\n{question}"]
    if company_name:
        parts.append(f"Company name: {company_name}")
    if role_title:
        parts.append(f"Requester role: {role_title}")
    if industry:
        parts.append(f"Industry: {industry}")
    if company_size:
        parts.append(f"Company size: {company_size}")
    if primary_systems:
        parts.append(
            "Primary systems (map architecture & integrations to these): "
            f"{primary_systems}"
        )
    if constraints:
        parts.append(f"Constraints: {constraints}")
    if success_metric:
        parts.append(f"Success metric: {success_metric}")
    if checklist_gap_summary:
        parts.append(f"Checklist gap summary:\n{checklist_gap_summary}")
    elif checklist_answers:
        lines = [
            f"- {qid}: {val}/5"
            for qid, val in sorted(checklist_answers.items())
        ]
        parts.append("Checklist answers:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def gap_summary_from_diagnosis(diagnosis: DiagnosisResult) -> str:
    gaps = "\n".join(f"- {g}" for g in diagnosis.top_gaps)
    return (
        f"Overall: {diagnosis.overall_readiness}\n"
        f"ACCESS {diagnosis.access.score}/10; "
        f"ADAPT {diagnosis.adapt.score}/10; "
        f"ADOPT {diagnosis.adopt.score}/10\n"
        f"Top gaps:\n{gaps}"
    )
