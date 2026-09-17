"""Shared user-context formatting for agent prompts."""

from __future__ import annotations

from typing import Optional


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
        parts.append(f"Primary systems: {primary_systems}")
    if constraints:
        parts.append(f"Constraints: {constraints}")
    if success_metric:
        parts.append(f"Success metric: {success_metric}")
    return "\n\n".join(parts)
