"""Collection workflow shared by the CLI and local web application."""

from collections.abc import Callable
from pathlib import Path

from payesh.database import (
    DEFAULT_DB_PATH, get_database_report, get_missing_pdf_downloads,
    save_announcement_file, save_announcements,
)
from payesh.extraction import extract_target_pdfs
from payesh.ifb import download_announcement_pdf, fetch_announcements


def collect(db_path: str | Path = DEFAULT_DB_PATH, page_url: str | None = None,
            progress: Callable[[str, int, int], None] | None = None) -> dict:
    """Collect current IFB rows and report download failures without discarding successes."""
    report = progress or (lambda stage, done, total: None)
    report("fetching", 0, 0)
    announcements = fetch_announcements(page_url=page_url) if page_url else fetch_announcements()
    save_announcements(announcements, db_path)
    missing = get_missing_pdf_downloads(db_path)
    downloaded = 0
    failures = []
    report("downloading", 0, len(missing))
    for index, (notice, url) in enumerate(missing):
        try:
            pdf = download_announcement_pdf(url)
            save_announcement_file(notice, pdf.filename, pdf.content, pdf.content_type, db_path)
            downloaded += 1
        except Exception as exc:
            failures.append({"notice_number": notice, "error": str(exc)})
        report("downloading", index + 1, len(missing))
    report("extracting", 0, 0)
    targets, complete, partial, daily = extract_target_pdfs(db_path)
    count, pdf_count, pdf_bytes = get_database_report(db_path)
    return {"announcements": announcements, "fetched": len(announcements), "downloaded": downloaded,
            "announcement_count": count, "pdf_count": pdf_count, "pdf_bytes": pdf_bytes,
            "target_count": targets, "complete_extractions": complete,
            "partial_extractions": partial, "daily_value_count": daily, "failures": failures}
