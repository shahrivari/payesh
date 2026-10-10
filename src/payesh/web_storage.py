"""Queries and durable collection-run state for the local dashboard."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import uuid

from payesh.database import _ensure_schema

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize(value: str) -> str:
    return value.translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").strip()


def date_key(value: str) -> str:
    """Normalize a source calendar date for ordering; never convert calendars implicitly."""
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", normalize(value))
    return "-".join(f"{int(part):02d}" for part in match.groups()) if match else ""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection(path: Path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.create_function("normalized", 1, normalize, deterministic=True)
    db.create_function("date_key", 1, date_key, deterministic=True)
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.execute("PRAGMA journal_mode = WAL")
        _ensure_schema(db)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS collection_runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                result_json TEXT,
                error TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_collection
                ON collection_runs ((1)) WHERE status = 'running';
        """)
        db.execute("""UPDATE collection_runs SET status='interrupted', stage='finished',
                      finished_at=?, error='Server stopped before collection finished.'
                      WHERE status='running'""", (now(),))


_JOIN = """FROM announcements a
           LEFT JOIN announcement_files f USING (notice_number)
           LEFT JOIN announcement_extractions e USING (notice_number)"""
_SELECT = """SELECT a.*, f.filename, f.downloaded_at,
             CASE WHEN f.file_id IS NULL THEN 0 ELSE 1 END AS has_pdf,
             e.document_type, COALESCE(e.extraction_status, 'none') AS extraction_status"""


def announcements(path: Path, *, page=1, page_size=20, q="", symbol="",
                  status="", document_type="", date_from="", date_to="") -> dict:
    clauses, values = [], []
    if q:
        clauses.append("(instr(normalized(a.symbol || ' ' || a.title || ' ' || a.notice_number), ?) > 0)")
        values.append(normalize(q))
    if symbol:
        clauses.append("normalized(a.symbol) = ?")
        values.append(normalize(symbol))
    if status:
        clauses.append("COALESCE(e.extraction_status, 'none') = ?")
        values.append(status)
    if document_type:
        clauses.append("e.document_type = ?")
        values.append(document_type)
    for operator, value in ((">=", date_from), ("<=", date_to)):
        if value:
            clauses.append(f"date_key(a.published_at) {operator} ?")
            values.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connection(path) as db:
        total = db.execute("SELECT COUNT(*) " + _JOIN + where, values).fetchone()[0]
        rows = db.execute(_SELECT + " " + _JOIN + where +
                          " ORDER BY date_key(a.published_at) DESC, a.last_seen_at DESC, a.notice_number DESC LIMIT ? OFFSET ?",
                          [*values, page_size, (page - 1) * page_size]).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def detail(path: Path, notice: str) -> dict | None:
    with connection(path) as db:
        row = db.execute(_SELECT + " " + _JOIN + " WHERE a.notice_number=?", (notice,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        extracted = db.execute("SELECT extracted_data_json, extracted_at FROM announcement_extractions WHERE notice_number=?", (notice,)).fetchone()
        result["extracted_data"] = json.loads(extracted[0]) if extracted else None
        result["extracted_at"] = extracted[1] if extracted else None
        result["daily_interest_values"] = [dict(item) for item in db.execute(
            "SELECT payment_date, amount_rial FROM daily_interest_values WHERE notice_number=? ORDER BY date_key(payment_date)", (notice,))]
    return result


def pdf(path: Path, notice: str) -> tuple | None:
    with connection(path) as db:
        row = db.execute("SELECT filename, file_blob FROM announcement_files WHERE notice_number=?", (notice,)).fetchone()
        return tuple(row) if row else None


def _run(row) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    serialized = result.pop("result_json")
    result["result"] = json.loads(serialized) if serialized else None
    return result


def get_run(path: Path, run_id: str) -> dict | None:
    with connection(path) as db:
        return _run(db.execute("SELECT * FROM collection_runs WHERE id=?", (run_id,)).fetchone())


def recent_runs(path: Path) -> list[dict]:
    with connection(path) as db:
        return [_run(row) for row in db.execute("SELECT * FROM collection_runs ORDER BY started_at DESC, rowid DESC LIMIT 20")]


def start_run(path: Path) -> str | None:
    run_id = uuid.uuid4().hex
    try:
        with connection(path) as db:
            db.execute("INSERT INTO collection_runs (id,status,stage,started_at) VALUES (?, 'running', 'fetching', ?)", (run_id, now()))
    except sqlite3.IntegrityError:
        return None
    return run_id


def progress(path: Path, run_id: str, stage: str, done: int, total: int) -> None:
    with connection(path) as db:
        db.execute("UPDATE collection_runs SET stage=?, done=?, total=? WHERE id=?", (stage, done, total, run_id))


def finish(path: Path, run_id: str, *, result=None, error=None) -> None:
    with connection(path) as db:
        db.execute("""UPDATE collection_runs SET status=?, stage='finished', finished_at=?,
                      result_json=?, error=? WHERE id=?""",
                   ("failed" if error else "partial" if result.get("failures") else "completed", now(),
                    json.dumps(result, ensure_ascii=False) if result else None, error, run_id))


def stats(path: Path) -> dict:
    with connection(path) as db:
        result = dict(db.execute("""SELECT
            (SELECT COUNT(*) FROM announcements) AS announcement_count,
            (SELECT COUNT(*) FROM announcement_files) AS pdf_count,
            (SELECT COALESCE(SUM(length(file_blob)),0) FROM announcement_files) AS pdf_bytes,
            (SELECT COUNT(*) FROM announcement_extractions WHERE extraction_status='complete') AS complete_count,
            (SELECT COUNT(*) FROM announcement_extractions WHERE extraction_status!='complete') AS review_count
        """).fetchone())
    runs = recent_runs(path)
    result["latest_run"] = runs[0] if runs else None
    return result
