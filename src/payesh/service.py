"""Collection workflow shared by the CLI and local web application."""

from collections.abc import Callable
from pathlib import Path

from payesh.database import (
    DEFAULT_DB_PATH, get_database_report, get_missing_pdf_downloads,
    save_announcement_file, save_announcements,
)
from payesh.extraction import extract_target_pdfs
from payesh.ifb import Announcement, download_announcement_pdf, fetch_announcements
from payesh import tse
from payesh.tse_extraction import extract_tse_attachments


def collect(db_path: str | Path = DEFAULT_DB_PATH, page_url: str | None = None,
            progress: Callable[[str, int, int], None] | None = None) -> dict:
    """Collect IFB and the newest TSE page independently, preserving successful work."""
    report = progress or (lambda stage, done, total: None)
    path = Path(db_path).expanduser()
    announcements = []
    failures = []
    sources = {}
    # Initialize storage even when a source is temporarily unavailable.
    save_announcements([], path)
    for source in ("ifb", "tse"):
        report(f"fetching_{source}", 0, 0)
        try:
            if source == "ifb":
                records = fetch_announcements(page_url=page_url) if page_url else fetch_announcements()
                save_announcements(records, path)
                announcements.extend(records)
            else:
                records = tse.fetch_announcements()
                tse.save_announcements(records, path)
                announcements.extend(Announcement(str(i), item.symbol, item.notice_number, item.title,
                                                  item.published_at, f"https://www.tse.ir/news/details/{item.source_id}")
                                     for i, item in enumerate(records, 1))
            sources[source] = {"fetched": len(records), "downloaded": 0, "status": "completed"}
        except Exception as exc:
            sources[source] = {"fetched": 0, "downloaded": 0, "status": "failed", "error": str(exc)}
            failures.append({"source": source, "notice_number": source, "error": str(exc)})
    missing = get_missing_pdf_downloads(db_path)
    downloaded = 0
    tse_missing = tse.missing_attachments(path)
    total = len(missing) + len(tse_missing)
    report("downloading_ifb", 0, total)
    for index, (notice, url) in enumerate(missing):
        try:
            pdf = download_announcement_pdf(url)
            save_announcement_file(notice, pdf.filename, pdf.content, pdf.content_type, db_path)
            downloaded += 1
            sources["ifb"]["downloaded"] += 1
        except Exception as exc:
            failures.append({"source": "ifb", "notice_number": notice, "error": str(exc)})
        report("downloading_ifb", index + 1, total)
    for index, file in enumerate(tse_missing):
        report("downloading_tse", len(missing) + index, total)
        try:
            content, mime = tse.download_attachment(file)
            tse.save_attachment(path, file["attachment_id"], content, mime)
            downloaded += 1
            sources["tse"]["downloaded"] += 1
        except Exception as exc:
            failures.append({"source": "tse", "notice_number": file["notice_number"],
                             "filename": file["filename"], "error": str(exc)})
        report("downloading_tse", len(missing) + index + 1, total)
    targets = complete = partial = daily = 0
    for source, extract in (("ifb", extract_target_pdfs), ("tse", extract_tse_attachments)):
        report(f"extracting_{source}", 0, 0)
        try:
            source_targets, source_complete, source_partial, source_daily = extract(path)
            targets += source_targets
            complete += source_complete
            partial += source_partial
            daily += source_daily
            sources[source]["extracted"] = source_targets
        except Exception as exc:
            failures.append({"source": source, "notice_number": source, "error": str(exc)})
    for source, result in sources.items():
        if result["status"] != "failed" and any(item["source"] == source for item in failures):
            result["status"] = "partial"
    if all(result["status"] == "failed" for result in sources.values()):
        raise RuntimeError("; ".join(f"{source}: {result['error']}" for source, result in sources.items()))
    count, pdf_count, pdf_bytes = get_database_report(db_path)
    return {"announcements": announcements, "fetched": len(announcements), "downloaded": downloaded,
            "announcement_count": count, "pdf_count": pdf_count, "pdf_bytes": pdf_bytes,
            "target_count": targets, "complete_extractions": complete,
            "partial_extractions": partial, "daily_value_count": daily, "failures": failures, "sources": sources}
