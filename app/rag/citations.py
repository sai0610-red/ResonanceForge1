"""Citation validation: keep only [D<n>:C<m>] markers that point at retrieved chunks."""

from __future__ import annotations

import re
from typing import Iterable

from app.models.schemas import (
    ArchitectureResult,
    DiagnosisResult,
    Evidence,
    EvidenceDocument,
    EvidencePassage,
)
from app.rag.retrieval import Hit

# One reference: D1:C2, D1-C2, D1 C2, D1, C2 (models vary). A bracket may hold several.
_REF = r"D\s*(\d+)\s*[:\-,]?\s*C\s*(\d+)"
_BRACKET_RE = re.compile(r"\s?\[\s*" + _REF + r"(?:\s*[,;]\s*" + _REF + r")*\s*\]", re.I)
_ONE_RE = re.compile(_REF, re.I)


def clean_text(text: str, valid: set[str], used: set[str]) -> tuple[str, int]:
    """Rewrite citation brackets in `text`: keep valid refs, drop unknown ones.

    Returns (new_text, dropped_count). Valid refs found are added to `used`.
    """
    dropped = 0

    def repl(match: re.Match) -> str:
        nonlocal dropped
        keep: list[str] = []
        for d, c in _ONE_RE.findall(match.group(0)):
            ref = f"D{int(d)}:C{int(c)}"
            if ref in valid:
                if ref not in keep:
                    keep.append(ref)
            else:
                dropped += 1
        if not keep:
            return ""
        used.update(keep)
        lead = " " if match.group(0)[:1].isspace() else ""
        return lead + "".join(f"[{r}]" for r in keep)

    return _BRACKET_RE.sub(repl, text or ""), dropped


def _clean_list(items: list[str], valid: set[str], used: set[str]) -> tuple[list[str], int]:
    out: list[str] = []
    dropped = 0
    for item in items:
        new, n = clean_text(item, valid, used)
        out.append(new)
        dropped += n
    return out, dropped


def ground_outputs(
    diagnosis: DiagnosisResult,
    architecture: ArchitectureResult,
    *,
    document_set_id: str,
    documents: Iterable[tuple[str, str]],
    diagnosis_hits: list[Hit],
    architect_hits: list[Hit],
) -> tuple[DiagnosisResult, ArchitectureResult, Evidence]:
    """Validate citations in agent text and build the report's Evidence section.

    A citation is valid only for the agent that was shown that passage, so the
    Architect cannot cite a chunk only the Diagnostician saw, and vice versa.
    """
    diag_valid = {h.item.ref for h in diagnosis_hits}
    arch_valid = {h.item.ref for h in architect_hits}
    used: set[str] = set()
    dropped = 0

    def c(text: str, valid: set[str]) -> str:
        nonlocal dropped
        new, n = clean_text(text, valid, used)
        dropped += n
        return new

    gaps, n = _clean_list(list(diagnosis.top_gaps), diag_valid, used)
    dropped += n
    diagnosis = diagnosis.model_copy(
        update={
            "access": diagnosis.access.model_copy(
                update={"reason": c(diagnosis.access.reason, diag_valid)}
            ),
            "adapt": diagnosis.adapt.model_copy(
                update={"reason": c(diagnosis.adapt.reason, diag_valid)}
            ),
            "adopt": diagnosis.adopt.model_copy(
                update={"reason": c(diagnosis.adopt.reason, diag_valid)}
            ),
            "top_gaps": gaps,
            "summary": c(diagnosis.summary, diag_valid),
        }
    )
    flow, n = _clean_list(list(architecture.high_level_flow), arch_valid, used)
    dropped += n
    agents = [
        a.model_copy(update={"responsibility": c(a.responsibility, arch_valid)})
        for a in architecture.recommended_agents
    ]
    architecture = architecture.model_copy(
        update={
            "recommended_agents": agents,
            "high_level_flow": flow,
            "rationale": c(architecture.rationale, arch_valid),
        }
    )

    passages: dict[str, EvidencePassage] = {}
    for agent, hits in (("diagnostician", diagnosis_hits), ("architect", architect_hits)):
        for h in hits:
            ref = h.item.ref
            if ref not in passages:
                passages[ref] = EvidencePassage(
                    ref=ref,
                    document=h.item.filename,
                    chunk=h.item.chunk,
                    score=round(h.score, 3),
                    text=h.item.text,
                    used_by=[agent],
                )
            elif agent not in passages[ref].used_by:
                passages[ref].used_by.append(agent)
    for ref, p in passages.items():
        p.cited = ref in used

    evidence = Evidence(
        document_set_id=document_set_id,
        documents=[EvidenceDocument(label=lbl, filename=fn) for lbl, fn in documents],
        passages=list(passages.values()),
        citations_dropped=dropped,
    )
    return diagnosis, architecture, evidence
