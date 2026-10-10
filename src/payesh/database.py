"""SQLite persistence for collected announcements."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from payesh.ifb import Announcement

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "payesh.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS announcements (
    notice_number TEXT PRIMARY KEY,
    row_number TEXT NOT NULL,
    symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT NOT NULL,
    file_url TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS announcement_files (
    file_id INTEGER PRIMARY KEY,
    notice_number TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_blob BLOB NOT NULL,
    downloaded_at TEXT NOT NULL,
    FOREIGN KEY (notice_number) REFERENCES announcements(notice_number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS announcement_extractions (
    notice_number TEXT PRIMARY KEY,
    document_type TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    extracted_data_json TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    FOREIGN KEY (notice_number) REFERENCES announcements(notice_number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_interest_values (
    notice_number TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    amount_rial TEXT,
    PRIMARY KEY (notice_number, payment_date),
    FOREIGN KEY (notice_number) REFERENCES announcements(notice_number) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_announcements_published_at
    ON announcements (published_at);
CREATE INDEX IF NOT EXISTS idx_announcements_symbol
    ON announcements (symbol);
"""


def _ensure_schema(connection: sqlite3.Connection) -> None:
    """Create the current database tables when they do not exist."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(announcements)")}
    for name, definition in {
        "source": "TEXT NOT NULL DEFAULT 'ifb'",
        "source_id": "TEXT NOT NULL DEFAULT ''",
        "source_calendar": "TEXT NOT NULL DEFAULT 'jalali'",
        "published_at_source": "TEXT NOT NULL DEFAULT ''",
        "abstract": "TEXT NOT NULL DEFAULT ''",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    }.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE announcements ADD COLUMN {name} {definition}")
    connection.execute("UPDATE announcements SET source_id=notice_number WHERE source_id=''")
    connection.execute("UPDATE announcements SET published_at_source=published_at WHERE published_at_source=''")
    connection.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_announcement_source ON announcements(source, source_id);
        CREATE TABLE IF NOT EXISTS source_attachments (
            attachment_id INTEGER PRIMARY KEY,
            notice_number TEXT NOT NULL REFERENCES announcements(notice_number) ON DELETE CASCADE,
            source_file_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_url TEXT NOT NULL,
            kind TEXT NOT NULL,
            content_type TEXT,
            file_blob BLOB,
            downloaded_at TEXT,
            extracted_data_json TEXT,
            extraction_status TEXT NOT NULL DEFAULT 'none',
            UNIQUE(notice_number, source_file_id)
        );
    """)


def save_announcements(
    announcements: list[Announcement],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Insert or refresh announcements and return the total number stored."""
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        connection.execute(
            "DELETE FROM announcements WHERE source='ifb' AND (file_url = '' OR file_url LIKE 'javascript:%')"
        )
        connection.executemany(
            """
            INSERT INTO announcements (
                notice_number, row_number, symbol, title, published_at,
                file_url, first_seen_at, last_seen_at, source_id, published_at_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(notice_number) DO UPDATE SET
                row_number = excluded.row_number,
                symbol = excluded.symbol,
                title = excluded.title,
                published_at = excluded.published_at,
                file_url = excluded.file_url,
                published_at_source = excluded.published_at_source,
                last_seen_at = excluded.last_seen_at
            """,
            [
                (
                    item.notice_number,
                    item.row_number,
                    item.symbol,
                    item.title,
                    item.published_at,
                    item.file_url,
                    now,
                    now,
                    item.notice_number,
                    item.published_at,
                )
                for item in announcements
            ],
        )
        row = connection.execute("SELECT COUNT(*) FROM announcements").fetchone()

    return int(row[0])


def get_missing_pdf_downloads(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[tuple[str, str]]:
    """Return notice numbers and URLs for records without a stored PDF."""
    path = Path(db_path).expanduser()
    if not path.exists():
        return []

    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT a.notice_number, a.file_url
            FROM announcements AS a
            LEFT JOIN announcement_files AS f USING (notice_number)
            WHERE f.file_id IS NULL AND a.source='ifb'
            ORDER BY a.last_seen_at DESC, CAST(a.row_number AS INTEGER) ASC
            """
        ).fetchall()
    return [(str(notice_number), str(file_url)) for notice_number, file_url in rows]


def save_announcement_file(
    notice_number: str,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Store a downloaded file BLOB separately from announcement metadata."""
    path = Path(db_path).expanduser()
    downloaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        cursor = connection.execute(
            """
            INSERT INTO announcement_files
                (notice_number, filename, content_type, file_blob, downloaded_at)
            SELECT notice_number, ?, ?, ?, ? FROM announcements
            WHERE notice_number = ?
            ON CONFLICT(notice_number) DO UPDATE SET
                filename = excluded.filename,
                content_type = excluded.content_type,
                file_blob = excluded.file_blob,
                downloaded_at = excluded.downloaded_at
            """,
            (filename, content_type, sqlite3.Binary(content), downloaded_at, notice_number),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"No announcement found for notice number {notice_number!r}.")


def get_database_report(db_path: str | Path = DEFAULT_DB_PATH) -> tuple[int, int, int]:
    """Return announcement count, PDF count, and total stored PDF bytes."""
    path = Path(db_path).expanduser()
    if not path.exists():
        return 0, 0, 0

    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        row = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM announcements), COUNT(*) +
                   (SELECT COUNT(*) FROM source_attachments WHERE kind='pdf' AND file_blob IS NOT NULL),
                   COALESCE(SUM(length(file_blob)), 0) +
                   (SELECT COALESCE(SUM(length(file_blob)),0) FROM source_attachments)
            FROM announcement_files
            """
        ).fetchone()
    return int(row[0]), int(row[1]), int(row[2])


def load_announcements(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[Announcement]:
    """Read stored announcements in their latest fetched table order."""
    path = Path(db_path).expanduser()
    if not path.exists():
        return []

    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT row_number, symbol, notice_number, title, published_at, file_url
            FROM announcements
            WHERE source='ifb'
            ORDER BY last_seen_at DESC, CAST(row_number AS INTEGER) ASC
            """
        ).fetchall()

    return [Announcement(*row) for row in rows]
