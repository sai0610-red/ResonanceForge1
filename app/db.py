"""SQLite persistence for ResonanceForge assessments."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings

DB_FILENAME = "resonanceforge.db"

# Path of the DB file that ensure_db() last initialized (None = not yet).
_initialized: Optional[Path] = None


def get_data_dir() -> Path:
    """DATA_DIR from settings (default ./data under the project root)."""
    return get_settings().data_path



def get_db_path() -> Path:
    return get_data_dir() / DB_FILENAME


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """WAL + a busy timeout so a backup or a second reader does not error immediately."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return str(uuid.uuid4())


def ensure_db() -> None:
    """Create data directory and assessments table if needed."""
    global _initialized
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        _apply_pragmas(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assessments (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                company_name TEXT,
                industry TEXT,
                company_size TEXT,
                role_title TEXT,
                primary_systems TEXT,
                constraints TEXT,
                success_metric TEXT,
                question TEXT NOT NULL,
                report_json TEXT,
                error TEXT,
                share_token TEXT UNIQUE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assessments_created_at ON assessments(created_at DESC)"
        )
        # Migrate: add checklist_json if missing (existing DBs)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(assessments)").fetchall()}
        if "checklist_json" not in cols:
            conn.execute("ALTER TABLE assessments ADD COLUMN checklist_json TEXT")
        if "document_set_id" not in cols:
            conn.execute("ALTER TABLE assessments ADD COLUMN document_set_id TEXT")
        # Customer documents (optional RAG grounding). Extracted text + chunks only.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_sets (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL REFERENCES document_sets(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL,
                char_count INTEGER NOT NULL,
                chunks_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_set ON documents(set_id)")
        conn.commit()
        _initialized = db_path
    finally:
        conn.close()


def ping() -> bool:
    """Health probe: True when a trivial SELECT 1 succeeds."""
    try:
        with _connect() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1
    except Exception:
        return False


@contextmanager
def _connect():
    db_path = get_db_path()
    if _initialized != db_path:
        ensure_db()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        _apply_pragmas(conn)
        yield conn
    finally:
        conn.close()


def create_assessment(
    *,
    question: str,
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    company_size: Optional[str] = None,
    role_title: Optional[str] = None,
    primary_systems: Optional[str] = None,
    constraints: Optional[str] = None,
    success_metric: Optional[str] = None,
    checklist: Optional[list] = None,
    status: str = "pending",
    document_set_id: Optional[str] = None,
) -> str:
    """Insert a new assessment row; return its id (also used as share_token)."""
    assessment_id = _new_id()
    created_at = _utc_now_iso()
    checklist_json = None
    if checklist is not None:
        if hasattr(checklist, "__iter__") and not isinstance(checklist, (str, bytes)):
            payload = []
            for item in checklist:
                if hasattr(item, "model_dump"):
                    payload.append(item.model_dump())
                elif isinstance(item, dict):
                    payload.append(item)
                else:
                    payload.append({"question_id": str(item), "value": 0})
            checklist_json = json.dumps(payload)
        else:
            checklist_json = json.dumps(checklist)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO assessments (
                id, created_at, status,
                company_name, industry, company_size, role_title,
                primary_systems, constraints, success_metric, question,
                report_json, error, share_token, checklist_json, document_set_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
            """,
            (
                assessment_id,
                created_at,
                status,
                company_name,
                industry,
                company_size,
                role_title,
                primary_systems,
                constraints,
                success_metric,
                question,
                assessment_id,
                checklist_json,
                document_set_id,
            ),
        )
        conn.commit()
    return assessment_id


def update_status(assessment_id: str, status: str, error: Optional[str] = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE assessments SET status = ?, error = ? WHERE id = ?",
            (status, error, assessment_id),
        )
        conn.commit()


def save_report(assessment_id: str, report: Any) -> None:
    """Persist completed report JSON and mark status=completed."""
    if hasattr(report, "model_dump"):
        payload = report.model_dump()
    elif isinstance(report, dict):
        payload = report
    else:
        payload = json.loads(str(report))
    report_json = json.dumps(payload)
    with _connect() as conn:
        conn.execute(
            """
            UPDATE assessments
            SET status = 'completed', report_json = ?, error = NULL
            WHERE id = ?
            """,
            (report_json, assessment_id),
        )
        conn.commit()


def get_by_id(assessment_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM assessments WHERE id = ?",
            (assessment_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_assessments(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, status, company_name, industry, company_size,
                   question, report_json
            FROM assessments
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_summary(row) for row in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    report = None
    raw = data.get("report_json")
    if raw:
        try:
            report = json.loads(raw)
        except json.JSONDecodeError:
            report = None
    data["report"] = report
    checklist = None
    craw = data.get("checklist_json")
    if craw:
        try:
            checklist = json.loads(craw)
        except json.JSONDecodeError:
            checklist = None
    data["checklist"] = checklist
    return data


def _row_to_summary(row: sqlite3.Row) -> dict[str, Any]:
    question = row["question"] or ""
    preview = question if len(question) <= 120 else question[:117] + "..."
    overall_readiness = None
    verdict = None
    raw = row["report_json"]
    if raw:
        try:
            report = json.loads(raw)
            diagnosis = report.get("diagnosis") or {}
            critique = report.get("critique") or {}
            overall_readiness = diagnosis.get("overall_readiness")
            verdict = critique.get("final_verdict")
        except json.JSONDecodeError:
            pass
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "company_name": row["company_name"],
        "industry": row["industry"],
        "company_size": row["company_size"],
        "question_preview": preview,
        "overall_readiness": overall_readiness,
        "verdict": verdict,
    }


# --- customer documents (RAG) ---


def create_document_set(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Store extracted documents as one set. Each item: filename, text, chunks (list[str]).

    Returns {"id", "created_at", "documents": [{label, filename, char_count, chunks}]}.
    """
    set_id = _new_id()
    created_at = _utc_now_iso()
    out = []
    with _connect() as conn:
        conn.execute(
            "INSERT INTO document_sets (id, created_at) VALUES (?, ?)", (set_id, created_at)
        )
        for i, doc in enumerate(documents, 1):
            label = f"D{i}"
            chunks = list(doc["chunks"])
            conn.execute(
                """
                INSERT INTO documents (id, set_id, label, filename, created_at,
                                       char_count, chunks_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id(),
                    set_id,
                    label,
                    doc["filename"],
                    created_at,
                    len(doc["text"]),
                    json.dumps(chunks),
                ),
            )
            out.append(
                {
                    "label": label,
                    "filename": doc["filename"],
                    "char_count": len(doc["text"]),
                    "chunks": len(chunks),
                }
            )
        conn.commit()
    return {"id": set_id, "created_at": created_at, "documents": out}


def get_document_set(set_id: str) -> Optional[dict[str, Any]]:
    """Return {"id", "created_at", "documents": [{label, filename, char_count, chunks}]}

    where chunks is the list of chunk texts, or None when the set does not exist.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, created_at FROM document_sets WHERE id = ?", (set_id,)
        ).fetchone()
        if row is None:
            return None
        docs = conn.execute(
            """
            SELECT label, filename, char_count, chunks_json FROM documents
            WHERE set_id = ? ORDER BY CAST(SUBSTR(label, 2) AS INTEGER)
            """,
            (set_id,),
        ).fetchall()
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "documents": [
            {
                "label": d["label"],
                "filename": d["filename"],
                "char_count": d["char_count"],
                "chunks": json.loads(d["chunks_json"]),
            }
            for d in docs
        ],
    }
