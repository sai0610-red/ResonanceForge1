"""SQLite persistence for ResonanceForge assessments."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "resonanceforge.db"

_initialized = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return str(uuid.uuid4())


def ensure_db() -> None:
    """Create data directory and assessments table if needed."""
    global _initialized
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    try:
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
        conn.commit()
        _initialized = True
    finally:
        conn.close()


@contextmanager
def _connect():
    if not _initialized:
        ensure_db()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
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
                report_json, error, share_token, checklist_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
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
