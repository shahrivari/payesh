"""Command-line entry point for Payesh."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from payesh.database import (
    DEFAULT_DB_PATH,
    get_database_report,
    get_missing_pdf_downloads,
    save_announcement_file,
    save_announcements,
)
from payesh.ifb import download_announcement_pdf, fetch_announcements, format_announcements
from payesh.extraction import extract_target_pdfs


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the IFB announcements table.")
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default=None,
        help="Also print fetched rows in this format (CSV or JSON).",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Page URL to fetch (defaults to the IFB announcements page).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH}).",
    )
    args = parser.parse_args()

    try:
        announcements = fetch_announcements(page_url=args.url) if args.url else fetch_announcements()
    except (RuntimeError, ValueError) as exc:
        print(f"payesh: {exc}", file=sys.stderr)
        return 1

    try:
        save_announcements(announcements, args.db)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"payesh: could not save announcements: {exc}", file=sys.stderr)
        return 1

    downloaded = 0
    failed: list[tuple[str, str]] = []
    for notice_number, file_url in get_missing_pdf_downloads(args.db):
        try:
            document = download_announcement_pdf(file_url)
            save_announcement_file(
                notice_number,
                document.filename,
                document.content,
                document.content_type,
                args.db,
            )
            downloaded += 1
        except (OSError, RuntimeError, sqlite3.Error, ValueError) as exc:
            failed.append((notice_number, str(exc)))

    announcement_count, pdf_count, pdf_bytes = get_database_report(args.db)
    try:
        target_count, complete_extractions, partial_extractions, daily_value_count = extract_target_pdfs(args.db)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"payesh: could not extract PDF data: {exc}", file=sys.stderr)
        return 1
    summary_lines = [
        "Payesh execution report",
        f"Announcements fetched this run: {len(announcements)}",
        f"Announcement records in database: {announcement_count}",
        f"PDFs downloaded and stored this run: {downloaded}",
        f"PDFs stored in database: {pdf_count}",
        f"Total PDF BLOB storage: {pdf_bytes:,} bytes",
        f"N-suffixed PDFs parsed: {target_count}",
        f"Complete extractions: {complete_extractions}",
        f"Partial or failed extractions: {partial_extractions}",
        f"Daily-interest values stored: {daily_value_count}",
        f"Database: {args.db.expanduser()}",
    ]
    if failed:
        summary_lines.append(f"PDF downloads failed: {len(failed)}")
        summary_lines.extend(f"  {notice_number}: {reason}" for notice_number, reason in failed)
    summary = "\n".join(summary_lines)

    if args.format:
        print(summary, file=sys.stderr)
        sys.stdout.write(format_announcements(announcements, args.format))
    else:
        print(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
