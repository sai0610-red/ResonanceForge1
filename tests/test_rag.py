"""Customer-document grounding: chunking, extraction, BM25 retrieval, citations, upload API.

No live Groq calls.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.api as api
from app.core.config import get_settings
from app.models.schemas import (
    AgentRole,
    ArchitectureResult,
    CodeGenerationResult,
    CritiqueResult,
    DiagnosisResult,
    ReadinessScore,
)
from app.rag.citations import clean_text, ground_outputs
from app.rag.documents import DocumentError, chunk_text, extract_text, safe_filename
from app.rag.retrieval import Hit, IndexedChunk, Retriever, format_passages, tokenize
from app.rubric.checklist import get_checklist_payload
from app.services.report import to_markdown

TOKEN = "test-demo-token"
GOOD = {"X-Demo-Token": TOKEN}

SOP = (
    "Returns SOP\n\n"
    "RMA requests arrive by email to returns@example.com and are keyed into the ERP "
    "by the customer service desk. The ERP is Epicor Kinetic.\n\n"
    "Credit memos above $5,000 need approval from the controller before posting.\n\n"
    "Quality inspection results are recorded on paper travelers and scanned weekly."
)


def make_pdf(text: str) -> bytes:
    """Minimal valid one-page PDF with a text stream (xref offsets computed)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


# --- chunking / extraction ---


def test_chunk_short_text_is_one_chunk():
    chunks = chunk_text("Hello world. Short note.")
    assert [c.index for c in chunks] == [1]
    assert chunks[0].text == "Hello world. Short note."


def test_chunk_packs_paragraphs_and_respects_size():
    paras = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(12))
    chunks = chunk_text(paras, chunk_chars=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c.text) <= 500 for c in chunks)
    assert [c.index for c in chunks] == list(range(1, len(chunks) + 1))
    joined = " ".join(c.text for c in chunks)
    for i in range(12):
        assert f"Paragraph {i} " in joined


def test_chunk_long_paragraph_overlaps():
    words = " ".join(f"w{i}" for i in range(600))
    chunks = chunk_text(words, chunk_chars=300, overlap=60)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 300 for c in chunks)
    # Last word of chunk 1 reappears at the start of chunk 2 (carry-over).
    last = chunks[0].text.split()[-1]
    assert last in chunks[1].text.split()[:15]


def test_extract_txt_md_and_pdf():
    assert "Epicor" in extract_text("sop.txt", SOP.encode())
    assert extract_text("notes.md", b"# Title\n\nBody   text").startswith("# Title")
    assert "Kinetic ERP backlog" in extract_text("x.pdf", make_pdf("Kinetic ERP backlog"))


@pytest.mark.parametrize(
    "name,data,status",
    [
        ("a.exe", b"MZ", 415),
        ("a.docx", b"PK", 415),
        ("a.pdf", b"not a pdf", 422),
        ("a.txt", b"\x00\x01\x02binary", 422),
        ("a.txt", b"   \n\n  ", 422),
    ],
)
def test_extract_rejects_bad_input(name, data, status):
    with pytest.raises(DocumentError) as exc:
        extract_text(name, data)
    assert exc.value.status == status


def test_safe_filename_strips_paths():
    assert safe_filename("../../etc/passwd.txt") == "passwd.txt"
    assert safe_filename("C:\\Users\\x\\plan<1>.md") == "plan_1_.md"
    assert safe_filename("") == "document"


# --- retrieval ---


def _index():
    items = [
        IndexedChunk("D1", "sop.txt", i, c.text) for i, c in enumerate(chunk_text(SOP, 200, 0), 1)
    ]
    items.append(IndexedChunk("D2", "it.md", 1, "Okta SSO and a Snowflake warehouse."))
    return Retriever(items)


def test_bm25_ranks_relevant_chunk_first():
    r = _index()
    hits = r.search("credit memo approval controller", k=2)
    assert hits and "controller" in hits[0].item.text
    assert r.search("snowflake warehouse", k=1)[0].item.ref == "D2:C1"


def test_bm25_no_match_and_empty_query():
    r = _index()
    assert r.search("zebra xylophone", k=3) == []
    assert r.search("", k=3) == []
    assert r.search("the and of", k=3) == []  # stopwords only


def test_bm25_is_deterministic():
    r = _index()
    a = [h.item.ref for h in r.search("ERP returns email", k=4)]
    b = [h.item.ref for h in r.search("ERP returns email", k=4)]
    assert a == b


def test_tokenize_drops_stopwords():
    assert tokenize("The ERP and the CRM") == ["erp", "crm"]


def test_format_passages_lists_labels():
    r = _index()
    block = format_passages(r.search("ERP", k=2))
    assert "[D1:C" in block and "Never invent a label" in block
    assert format_passages([]) == ""


# --- citations ---


def test_clean_text_keeps_valid_and_drops_unknown():
    used: set[str] = set()
    text, dropped = clean_text(
        "Email intake [D1:C1]. Approval rule [D1-C2]. Made up [D9:C9]. Both [D1:C1, D4:C2].",
        {"D1:C1", "D1:C2"},
        used,
    )
    assert text == "Email intake [D1:C1]. Approval rule [D1:C2]. Made up. Both [D1:C1]."
    assert dropped == 2
    assert used == {"D1:C1", "D1:C2"}


def test_clean_text_leaves_other_brackets_alone():
    used: set[str] = set()
    text, dropped = clean_text("Step [1] then [optional] review.", {"D1:C1"}, used)
    assert text == "Step [1] then [optional] review."
    assert dropped == 0


def _diag(reason="r"):
    s = ReadinessScore(score=5, reason=reason)
    return DiagnosisResult(
        access=s, adapt=s, adopt=s, overall_readiness="Medium",
        top_gaps=["g1 [D1:C1]", "g2", "g3"], summary="s [D2:C1]",
    )


def _arch(rationale):
    return ArchitectureResult(
        recommended_agents=[AgentRole(name="Intake", responsibility="Parse RMA emails [D1:C1]")],
        high_level_flow=["START", "Intake [D7:C1]", "END"],
        rationale=rationale,
        estimated_complexity="Low",
    )


def test_ground_outputs_scopes_citations_per_agent():
    r = _index()
    d1 = r.chunks[0]
    d2 = r.chunks[-1]
    diag_hits = [Hit(d1, 2.0)]
    arch_hits = [Hit(d1, 2.0), Hit(d2, 1.0)]
    diagnosis, arch, ev = ground_outputs(
        _diag(),
        _arch("Uses the email intake [D1:C1] and warehouse [D2:C1]."),
        document_set_id="set-1",
        documents=[("D1", "sop.txt"), ("D2", "it.md")],
        diagnosis_hits=diag_hits,
        architect_hits=arch_hits,
    )
    # D2:C1 was only shown to the Architect, so the Diagnostician may not cite it.
    assert diagnosis.summary == "s"
    assert diagnosis.top_gaps[0] == "g1 [D1:C1]"
    assert arch.rationale.endswith("[D2:C1].")
    assert arch.high_level_flow[1] == "Intake"
    assert ev.citations_dropped == 2
    refs = {p.ref: p for p in ev.passages}
    assert set(refs) == {"D1:C1", "D2:C1"}
    assert refs["D1:C1"].used_by == ["diagnostician", "architect"]
    assert refs["D1:C1"].cited and refs["D2:C1"].cited


# --- API ---


def _answers():
    return [{"question_id": q["id"], "value": 3} for q in get_checklist_payload()]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_TOKEN", TOKEN)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "50")
    monkeypatch.setenv("RAG_MAX_FILES", "3")
    monkeypatch.setenv("RAG_MAX_FILE_BYTES", "5000")
    monkeypatch.setenv("ENV", "development")
    get_settings.cache_clear()
    api.rate_limiter.reset()
    api.upload_limiter.reset()
    captured: dict = {}

    def fake_diag(**kwargs):
        captured["diagnostician"] = kwargs
        return _diag()

    def fake_arch(**kwargs):
        captured["architect"] = kwargs
        return _arch("Grounded in [D1:C1]; invented [D3:C4].")

    def fake_code(**kwargs):
        return CodeGenerationResult(
            code="from langgraph.graph import StateGraph\ng = StateGraph(dict)\napp = g.compile()\n",
            explanation="e",
        )

    def fake_critic(**kwargs):
        captured["critic"] = kwargs
        return CritiqueResult(
            strengths=["s"], weaknesses=["w"], risks=["r"], recommendations=["x"],
            final_verdict="Needs work",
        )

    monkeypatch.setattr(api, "run_diagnostician", fake_diag)
    monkeypatch.setattr(api, "run_architect", fake_arch)
    monkeypatch.setattr(api, "run_code_generator", fake_code)
    monkeypatch.setattr(api, "run_critic", fake_critic)
    # The sync /assess path goes through the LangGraph graph module.
    import app.graphs.resonance_graph as graph

    monkeypatch.setattr(graph, "run_diagnostician", fake_diag)
    monkeypatch.setattr(graph, "run_architect", fake_arch)
    monkeypatch.setattr(graph, "run_code_generator", fake_code)
    monkeypatch.setattr(graph, "run_critic", fake_critic)
    with TestClient(api.app) as c:
        c.captured = captured
        yield c
    api.rate_limiter.reset()
    api.upload_limiter.reset()
    get_settings.cache_clear()


def _upload(client, files, headers=GOOD):
    return client.post(
        "/api/documents",
        headers=headers,
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def test_upload_requires_token(client):
    r = _upload(client, [("sop.txt", SOP.encode())], headers={})
    assert r.status_code == 401
    r = _upload(client, [("sop.txt", SOP.encode())], headers={"X-Demo-Token": "wrong"})
    assert r.status_code == 401


def test_upload_returns_set_and_metadata(client):
    r = _upload(client, [("sop.txt", SOP.encode()), ("plan.pdf", make_pdf("Pilot plan"))])
    assert r.status_code == 200, r.text
    body = r.json()
    assert [d["label"] for d in body["documents"]] == ["D1", "D2"]
    assert body["documents"][0]["chunks"] >= 1
    meta = client.get(f"/api/documents/{body['document_set_id']}", headers=GOOD)
    assert meta.status_code == 200
    assert meta.json()["documents"][1]["filename"] == "plan.pdf"
    assert client.get(f"/api/documents/{body['document_set_id']}").status_code == 401
    assert client.get("/api/documents/nope", headers=GOOD).status_code == 404


def test_upload_limits(client):
    assert _upload(client, [("big.txt", b"a " * 3000)]).status_code == 413
    four = [(f"f{i}.txt", b"text") for i in range(4)]
    assert _upload(client, four).status_code == 413
    assert _upload(client, [("x.docx", b"PK..")]).status_code == 415
    assert _upload(client, [("x.pdf", b"garbage")]).status_code == 422


def test_upload_rate_limit(client, monkeypatch):
    monkeypatch.setenv("UPLOAD_RATE_LIMIT_PER_HOUR", "1")
    get_settings.cache_clear()
    assert _upload(client, [("a.txt", b"one")]).status_code == 200
    r = _upload(client, [("a.txt", b"two")])
    assert r.status_code == 429 and r.headers.get("Retry-After")


def _stream(client, body):
    r = client.post("/api/assessments/stream", headers=GOOD, json=body)
    assert r.status_code == 200, r.text
    import json

    events = [blk for blk in r.text.split("\n\n") if blk.startswith("event: complete")]
    assert events, r.text
    return json.loads(events[0].split("data: ", 1)[1])


def test_stream_with_documents_grounds_architect_and_validates_citations(client):
    up = _upload(client, [("returns-sop.txt", SOP.encode())]).json()
    done = _stream(
        client,
        {
            "question": "Automate RMA returns intake and credit memo approval in the ERP",
            "checklist": _answers(),
            "document_set_id": up["document_set_id"],
        },
    )
    arch_prompt = client.captured["architect"]["passages"]
    assert arch_prompt and "[D1:C1]" in arch_prompt and "returns-sop.txt" in arch_prompt
    # Complete checklist -> rubric path, no passages sent to the diagnostician.
    assert client.captured["diagnostician"]["passages"] is None
    report = done["report"]
    assert report["evidence"]["document_set_id"] == up["document_set_id"]
    assert report["architecture"]["rationale"] == "Grounded in [D1:C1]; invented."
    assert report["evidence"]["citations_dropped"] >= 1
    assert any(p["cited"] for p in report["evidence"]["passages"])
    # Critic only sees validated text.
    assert "[D3:C4]" not in client.captured["critic"]["architecture"].rationale
    rec = client.get(f"/api/assessments/{done['id']}", headers=GOOD).json()
    assert rec["document_set_id"] == up["document_set_id"]
    shared = client.get(f"/api/reports/{done['id']}").json()
    assert shared["report"]["evidence"]["passages"]


def test_incomplete_checklist_sends_passages_to_diagnostician(client):
    up = _upload(client, [("returns-sop.txt", SOP.encode())]).json()
    _stream(
        client,
        {"question": "RMA returns intake via email into the ERP", "document_set_id": up["document_set_id"]},
    )
    assert "[D1:C" in (client.captured["diagnostician"]["passages"] or "")


def test_no_documents_is_unchanged(client):
    done = _stream(client, {"question": "Automate returns", "checklist": _answers()})
    assert client.captured["architect"]["passages"] is None
    assert done["report"]["evidence"] is None
    # Without documents no citation filtering happens, matching previous behaviour.
    assert done["report"]["architecture"]["rationale"] == "Grounded in [D1:C1]; invented [D3:C4]."


def test_unknown_document_set_is_422(client):
    r = client.post(
        "/api/assessments/stream",
        headers=GOOD,
        json={"question": "x", "checklist": _answers(), "document_set_id": "missing"},
    )
    assert r.status_code == 422


def test_sync_assess_path_grounds_via_graph(client):
    up = _upload(client, [("returns-sop.txt", SOP.encode())]).json()
    r = client.post(
        "/assess",
        headers=GOOD,
        json={
            "question": "Automate RMA returns intake",
            "checklist": _answers(),
            "document_set_id": up["document_set_id"],
        },
    )
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["evidence"]["passages"]
    assert "[D3:C4]" not in report["architecture"]["rationale"]


def test_markdown_has_evidence_section(client):
    up = _upload(client, [("returns-sop.txt", SOP.encode())]).json()
    done = _stream(
        client,
        {"question": "RMA returns intake", "checklist": _answers(), "document_set_id": up["document_set_id"]},
    )
    from app.models.schemas import ResonanceReport

    md = to_markdown(ResonanceReport.model_validate(done["report"]))
    assert "## Evidence" in md and "[D1:C1]" in md and "returns-sop.txt" in md
