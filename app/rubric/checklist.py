"""Fixed 15-question ACCESS / ADAPT / ADOPT checklist and deterministic scorer."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict

from app.models.schemas import DiagnosisResult, ReadinessScore

Dimension = Literal["access", "adapt", "adopt"]


class ChecklistOption(TypedDict):
    value: int
    label: str


class ChecklistItem(TypedDict):
    id: str
    dimension: Dimension
    prompt: str
    options: List[ChecklistOption]
    short_label: str
    gap_hint: str


def _opts(
    a1: str,
    a2: str,
    a3: str,
    a4: str,
    a5: str,
) -> List[ChecklistOption]:
    return [
        {"value": 1, "label": a1},
        {"value": 2, "label": a2},
        {"value": 3, "label": a3},
        {"value": 4, "label": a4},
        {"value": 5, "label": a5},
    ]


CHECKLIST: List[ChecklistItem] = [
    # --- ACCESS (5) ---
    {
        "id": "access_data_quality",
        "dimension": "access",
        "short_label": "Data quality",
        "gap_hint": "Improve data quality (completeness, accuracy, lineage) before agent workflows rely on it.",
        "prompt": "How would you rate the quality and trustworthiness of the data agents would need?",
        "options": _opts(
            "Critical gaps — incomplete, conflicting, or undocumented data",
            "Weak — frequent cleanup needed; limited lineage",
            "Adequate — usable with known caveats",
            "Strong — mostly clean with documented ownership",
            "Excellent — high quality, lineage, and SLAs in place",
        ),
    },
    {
        "id": "access_unified_apis",
        "dimension": "access",
        "short_label": "Unified access APIs",
        "gap_hint": "Expose stable, documented APIs (or an integration layer) so agents can retrieve and act on core systems.",
        "prompt": "Do you have unified, documented APIs or an integration layer for core systems?",
        "options": _opts(
            "No — mostly UI scraping, files, or tribal knowledge",
            "Fragmented — a few APIs, many point-to-point scripts",
            "Partial — key systems API-enabled; others manual",
            "Mostly unified — API gateway / iPaaS covers primary systems",
            "Fully unified — governed APIs with contracts and versioning",
        ),
    },
    {
        "id": "access_pii_governance",
        "dimension": "access",
        "short_label": "PII / data governance",
        "gap_hint": "Stand up PII classification, access controls, and retention rules before agents touch sensitive data.",
        "prompt": "How mature is PII classification, access control, and data governance for AI use?",
        "options": _opts(
            "None — sensitive data mixed without controls",
            "Ad hoc — policies exist but rarely enforced",
            "Developing — classification started; uneven enforcement",
            "Mature — roles, masking, and audit trails for most sensitive data",
            "Enterprise-grade — continuous compliance with clear AI data policies",
        ),
    },
    {
        "id": "access_latency_freshness",
        "dimension": "access",
        "short_label": "Latency / freshness",
        "gap_hint": "Close the gap between batch/stale feeds and the freshness agents need for reliable decisions.",
        "prompt": "Can agents get data that is fresh enough for the decisions they would make?",
        "options": _opts(
            "Days-old batches only — decisions would be stale",
            "Mostly overnight batches; limited near-real-time paths",
            "Mixed — some streams, many delayed warehouse loads",
            "Near real-time for critical domains",
            "Realtime / low-latency feeds with freshness SLOs",
        ),
    },
    {
        "id": "access_integrations",
        "dimension": "access",
        "short_label": "Tool / system integrations",
        "gap_hint": "Prioritize reliable connectors to the systems named in intake so agents can act, not just advise.",
        "prompt": "How ready are integrations to the tools and systems agents must call (ERP, CRM, tickets, etc.)?",
        "options": _opts(
            "No reliable connectors — manual handoffs only",
            "Brittle scripts for 1–2 systems",
            "Working integrations for a subset of named systems",
            "Solid connectors for most primary systems",
            "Production-grade integrations with monitoring and retries",
        ),
    },
    # --- ADAPT (5) ---
    {
        "id": "adapt_ai_strategy",
        "dimension": "adapt",
        "short_label": "AI strategy",
        "gap_hint": "Define a clear multi-agent / AI strategy tied to business outcomes and prioritized use cases.",
        "prompt": "Is there a clear AI / multi-agent strategy tied to business outcomes?",
        "options": _opts(
            "No strategy — AI interest is anecdotal",
            "Informal ideas without prioritized use cases",
            "Draft strategy; limited alignment across teams",
            "Published strategy with prioritized pilots",
            "Board-visible strategy with roadmap and KPIs",
        ),
    },
    {
        "id": "adapt_talent_partners",
        "dimension": "adapt",
        "short_label": "Talent / partners",
        "gap_hint": "Build or contract AI/ML + platform talent (and partners) who can own agent design and ops.",
        "prompt": "Do you have internal talent or trusted partners to design and operate agent systems?",
        "options": _opts(
            "No AI/ML or platform capacity",
            "One enthusiast; no bench or partner",
            "Small team or partner engaged for pilots",
            "Cross-functional squad with partner backup",
            "Dedicated platform + domain team with partner ecosystem",
        ),
    },
    {
        "id": "adapt_change_management",
        "dimension": "adapt",
        "short_label": "Change management",
        "gap_hint": "Invest in change management so workflows and roles absorb agent-assisted processes safely.",
        "prompt": "How strong is change management for new AI-assisted workflows?",
        "options": _opts(
            "None — tools are dropped on teams without support",
            "Reactive training after pushback",
            "Some playbooks; inconsistent rollout",
            "Structured change plans for major AI initiatives",
            "Institutionalized change office with adoption metrics",
        ),
    },
    {
        "id": "adapt_exec_sponsorship",
        "dimension": "adapt",
        "short_label": "Exec sponsorship",
        "gap_hint": "Secure an executive sponsor who can unblock budget, data access, and cross-team decisions.",
        "prompt": "Is there active executive sponsorship for an AI agent pilot?",
        "options": _opts(
            "No sponsor — AI is a side project",
            "Passive awareness without decisions",
            "Sponsor named but bandwidth-limited",
            "Active sponsor with regular steering",
            "C-level ownership with clear accountability",
        ),
    },
    {
        "id": "adapt_pilot_budget",
        "dimension": "adapt",
        "short_label": "Pilot budget",
        "gap_hint": "Ring-fence budget for a time-boxed pilot (people, infra, LLM spend) with a go/no-go gate.",
        "prompt": "Is budget allocated for a time-boxed multi-agent pilot (people, infra, LLM spend)?",
        "options": _opts(
            "No budget — must steal time from BAU",
            "Wish-list only; no approved spend",
            "Limited discretionary spend for experiments",
            "Approved pilot budget with clear scope",
            "Funded program with contingency and renewals",
        ),
    },
    # --- ADOPT (5) ---
    {
        "id": "adopt_security_compliance",
        "dimension": "adopt",
        "short_label": "Security / compliance",
        "gap_hint": "Align security and compliance (LLM usage, data residency, audit) before production agent traffic.",
        "prompt": "How ready are security and compliance reviews for LLM / agent workloads?",
        "options": _opts(
            "Blockers — no path for LLM tools in production",
            "Unclear policy; reviews would stall a pilot",
            "Known path with lengthy exception process",
            "Documented AI security checklist and review SLA",
            "Pre-approved patterns for agent workloads",
        ),
    },
    {
        "id": "adopt_observability",
        "dimension": "adopt",
        "short_label": "Observability",
        "gap_hint": "Add tracing, logging, and cost/latency dashboards so agent failures are visible and diagnosable.",
        "prompt": "Can you observe, trace, and alert on AI / agent workloads today?",
        "options": _opts(
            "No — black-box scripts and chat logs only",
            "Basic app logs; no agent-specific traces",
            "Partial metrics for one or two AI services",
            "Tracing + dashboards for pilot services",
            "Full observability with cost, latency, and quality signals",
        ),
    },
    {
        "id": "adopt_human_in_loop",
        "dimension": "adopt",
        "short_label": "Human-in-the-loop ops",
        "gap_hint": "Design human-in-the-loop review queues and escalation paths for high-impact agent actions.",
        "prompt": "Are human-in-the-loop review and escalation paths defined for agent actions?",
        "options": _opts(
            "No — automation would be fully unsupervised",
            "Informal review by whoever is available",
            "Pilot review queue without SLAs",
            "Defined HITL gates for high-impact actions",
            "Mature ops with SLAs, audit, and override playbooks",
        ),
    },
    {
        "id": "adopt_eval_testing",
        "dimension": "adopt",
        "short_label": "Eval / testing culture",
        "gap_hint": "Build an evaluation and regression-test culture (golden sets, failure cases) for agent quality.",
        "prompt": "Do you have an evaluation / testing culture for AI outputs (golden sets, regression)?",
        "options": _opts(
            "No evals — ship and hope",
            "Ad hoc spot-checks",
            "Some test cases; not automated",
            "Golden sets + regression for key flows",
            "Continuous eval with quality gates in CI",
        ),
    },
    {
        "id": "adopt_production_ownership",
        "dimension": "adopt",
        "short_label": "Production ownership",
        "gap_hint": "Name an owning team with on-call and runbooks before treating the pilot as production software.",
        "prompt": "Is there a named team that will own the agent system in production (on-call, runbooks)?",
        "options": _opts(
            "No owner — project would become orphanware",
            "Vendor or consultant owns it temporarily",
            "Informal ownership inside one squad",
            "Named product + platform owners for the pilot",
            "Clear RACI, on-call, and runbooks ready",
        ),
    },
]

_CHECKLIST_BY_ID: Dict[str, ChecklistItem] = {item["id"]: item for item in CHECKLIST}


def get_checklist_payload() -> List[Dict[str, Any]]:
    """API-friendly checklist (id, dimension, prompt, options)."""
    return [
        {
            "id": item["id"],
            "dimension": item["dimension"],
            "prompt": item["prompt"],
            "options": item["options"],
        }
        for item in CHECKLIST
    ]


def is_checklist_complete(answers: Dict[str, int] | None) -> bool:
    if not answers:
        return False
    for item in CHECKLIST:
        val = answers.get(item["id"])
        if val is None or not isinstance(val, int) or val < 1 or val > 5:
            return False
    return True


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _dim_score(values: List[int]) -> int:
    avg = sum(values) / len(values)
    return _clamp(int(round(avg * 2)), 1, 10)


def _overall_band(mean_score: float) -> Literal["Low", "Medium", "High"]:
    if mean_score < 4.5:
        return "Low"
    if mean_score < 7.5:
        return "Medium"
    return "High"


def _reason_for_dimension(
    dimension: Dimension, answers: Dict[str, int]
) -> str:
    parts: List[str] = []
    for item in CHECKLIST:
        if item["dimension"] != dimension:
            continue
        val = answers[item["id"]]
        parts.append(f"{item['short_label']}={val}/5")
    joined = "; ".join(parts)
    return f"Checklist-driven: {joined}."


def score_checklist(answers: Dict[str, int]) -> DiagnosisResult:
    """
    Deterministic ACCESS / ADAPT / ADOPT scoring from 15 checklist answers (1–5).

    Per dimension: avg of 5 answers → map to 1–10 via round(avg * 2), clamped.
    Overall: mean of three dimension scores; Low <4.5, Medium <7.5, else High.
    """
    if not is_checklist_complete(answers):
        missing = [i["id"] for i in CHECKLIST if answers.get(i["id"]) is None]
        raise ValueError(
            f"Incomplete checklist; need all 15 answers. Missing: {missing or 'invalid values'}"
        )

    by_dim: Dict[Dimension, List[int]] = {
        "access": [],
        "adapt": [],
        "adopt": [],
    }
    for item in CHECKLIST:
        by_dim[item["dimension"]].append(int(answers[item["id"]]))

    access_s = _dim_score(by_dim["access"])
    adapt_s = _dim_score(by_dim["adapt"])
    adopt_s = _dim_score(by_dim["adopt"])
    mean = (access_s + adapt_s + adopt_s) / 3.0
    overall = _overall_band(mean)

    # Lowest-scoring questions → top gaps (3–5)
    scored_items = []
    for item in CHECKLIST:
        scored_items.append((int(answers[item["id"]]), item))
    scored_items.sort(key=lambda t: (t[0], t[1]["id"]))
    n_gaps = 5 if scored_items[0][0] <= 2 else 3
    n_gaps = max(3, min(5, n_gaps))
    # Always take at least the 3 lowest; up to 5 if many weak scores
    weak = [it for v, it in scored_items if v <= 3]
    if len(weak) >= 3:
        gap_items = weak[:5]
    else:
        gap_items = [it for _, it in scored_items[: max(3, min(5, len(scored_items)))]]

    top_gaps = [
        f"{item['short_label']}: {item['gap_hint']}" for item in gap_items
    ]

    summary = (
        f"Checklist-based readiness is {overall} "
        f"(ACCESS {access_s}/10, ADAPT {adapt_s}/10, ADOPT {adopt_s}/10; "
        f"mean {mean:.1f}/10). "
        f"Lowest-scoring areas: {', '.join(i['short_label'] for i in gap_items[:3])}. "
        f"Use the gaps below to scope a 90-day pilot against named systems and ownership."
    )

    return DiagnosisResult(
        access=ReadinessScore(
            score=access_s, reason=_reason_for_dimension("access", answers)
        ),
        adapt=ReadinessScore(
            score=adapt_s, reason=_reason_for_dimension("adapt", answers)
        ),
        adopt=ReadinessScore(
            score=adopt_s, reason=_reason_for_dimension("adopt", answers)
        ),
        overall_readiness=overall,
        top_gaps=top_gaps,
        summary=summary,
    )


def answers_from_checklist_list(
    checklist: List[Any] | None,
) -> Dict[str, int]:
    """Normalize ChecklistAnswer list / dicts into {question_id: value}."""
    out: Dict[str, int] = {}
    if not checklist:
        return out
    for item in checklist:
        if hasattr(item, "question_id"):
            qid = item.question_id
            val = int(item.value)
        elif isinstance(item, dict):
            qid = item.get("question_id") or item.get("id")
            val = int(item.get("value"))
        else:
            continue
        if qid:
            out[str(qid)] = val
    return out


def format_gap_summary(diagnosis: DiagnosisResult) -> str:
    gaps = "\n".join(f"- {g}" for g in diagnosis.top_gaps)
    return (
        f"Overall: {diagnosis.overall_readiness}\n"
        f"ACCESS {diagnosis.access.score}/10; "
        f"ADAPT {diagnosis.adapt.score}/10; "
        f"ADOPT {diagnosis.adopt.score}/10\n"
        f"Top gaps:\n{gaps}"
    )
