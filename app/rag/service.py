"""Glue between the API / graph and the RAG pieces: ingest, load, retrieve, ground."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from app import db
from app.core.config import get_settings
from app.models.schemas import ArchitectureResult, DiagnosisResult, Evidence
from app.rag.citations import ground_outputs
from app.rag.documents import DocumentError, check_extension, chunk_text, extract_text, safe_filename
from app.rag.retrieval import Hit, IndexedChunk, Retriever, build_query, format_passages
from app.rubric.checklist import answers_from_checklist_list, is_checklist_complete


def ingest(files: Sequence[tuple[str, bytes]]) -> dict[str, Any]:
    """Validate, extract, chunk and store uploaded files as one document set.

    `files` is (original_filename, bytes). Raises DocumentError (status 413/415/422).
    """
    settings = get_settings()
    if not files:
        raise DocumentError("Upload at least one file (field name: files)")
    if len(files) > settings.rag_max_files:
        raise DocumentError(
            f"Too many files ({len(files)}); maximum is {settings.rag_max_files}", status=413
        )
    docs = []
    total = 0
    for raw_name, data in files:
        name = safe_filename(raw_name)
        check_extension(name)
        if len(data) > settings.rag_max_file_bytes:
            raise DocumentError(
                f"{name}: file is {len(data)} bytes; maximum is {settings.rag_max_file_bytes}",
                status=413,
            )
        text = extract_text(name, data)
        total += len(text)
        if total > settings.rag_max_total_chars:
            raise DocumentError(
                f"Extracted text exceeds {settings.rag_max_total_chars} characters in total",
                status=413,
            )
        chunks = chunk_text(text, settings.rag_chunk_chars, settings.rag_chunk_overlap)
        docs.append({"filename": name, "text": text, "chunks": [c.text for c in chunks]})
    return db.create_document_set(docs)


@dataclass
class Grounding:
    """Per-assessment retrieval state. `retriever` is None when no documents were given."""

    document_set_id: Optional[str] = None
    documents: list[tuple[str, str]] = field(default_factory=list)
    retriever: Optional[Retriever] = None
    diagnosis_hits: list[Hit] = field(default_factory=list)
    architect_hits: list[Hit] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.retriever is not None and len(self.retriever) > 0


def load(document_set_id: Optional[str]) -> Grounding:
    """Build a retriever for a stored set. Unknown id raises DocumentError(404)."""
    if not document_set_id:
        return Grounding()
    record = db.get_document_set(document_set_id)
    if record is None:
        raise DocumentError("document_set_id not found", status=404)
    items: list[IndexedChunk] = []
    docs: list[tuple[str, str]] = []
    for d in record["documents"]:
        docs.append((d["label"], d["filename"]))
        for i, text in enumerate(d["chunks"], 1):
            items.append(IndexedChunk(doc_label=d["label"], filename=d["filename"], chunk=i, text=text))
    return Grounding(document_set_id=record["id"], documents=docs, retriever=Retriever(items))


def _intake_query(question: str, intake: Mapping[str, Any]) -> str:
    return build_query(
        question,
        intake.get("industry"),
        intake.get("primary_systems"),
        intake.get("constraints"),
        intake.get("success_metric"),
    )


def retrieve_for_diagnosis(g: Grounding, question: str, intake: Mapping[str, Any]) -> list[Hit]:
    if not g.active:
        return []
    g.diagnosis_hits = g.retriever.search(_intake_query(question, intake), get_settings().rag_top_k)
    return g.diagnosis_hits


def retrieve_for_architect(
    g: Grounding, question: str, intake: Mapping[str, Any], diagnosis: DiagnosisResult
) -> list[Hit]:
    """Query with the situation plus the diagnosed gaps, so passages match what to fix."""
    if not g.active:
        return []
    query = build_query(_intake_query(question, intake), extra=diagnosis.top_gaps)
    g.architect_hits = g.retriever.search(query, get_settings().rag_top_k)
    return g.architect_hits


def ground(
    g: Grounding, diagnosis: DiagnosisResult, architecture: ArchitectureResult
) -> tuple[DiagnosisResult, ArchitectureResult, Optional[Evidence]]:
    """Validate citations and build Evidence. No-op (evidence None) without documents."""
    if not g.document_set_id:
        return diagnosis, architecture, None
    return ground_outputs(
        diagnosis,
        architecture,
        document_set_id=g.document_set_id,
        documents=g.documents,
        diagnosis_hits=g.diagnosis_hits,
        architect_hits=g.architect_hits,
    )




def needs_llm_diagnosis(checklist: Any) -> bool:
    """True when the Diagnostician will call the LLM (checklist missing or incomplete)."""
    if isinstance(checklist, dict):
        answers = {str(k): int(v) for k, v in checklist.items()}
    else:
        answers = answers_from_checklist_list(checklist)
    return not is_checklist_complete(answers)


def passages_block(hits: list[Hit]) -> Optional[str]:
    return format_passages(hits) or None


__all__ = [
    "DocumentError",
    "needs_llm_diagnosis",
    "passages_block",
    "Grounding",
    "ground",
    "ingest",
    "load",
    "retrieve_for_architect",
    "retrieve_for_diagnosis",
]
