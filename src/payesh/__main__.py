"""Command-line entry point for Payesh."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from payesh.database import DEFAULT_DB_PATH
from payesh.ifb import format_announcements
from payesh.service import collect


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
        result = collect(args.db, args.url)
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as exc:
        print(f"payesh: {exc}", file=sys.stderr)
        return 1
    announcements = result["announcements"]
    downloaded = result["downloaded"]
    failed = [(item["notice_number"], item["error"]) for item in result["failures"]]
    announcement_count = result["announcement_count"]
    pdf_count = result["pdf_count"]
    pdf_bytes = result["pdf_bytes"]
    target_count = result["target_count"]
    complete_extractions = result["complete_extractions"]
    partial_extractions = result["partial_extractions"]
    daily_value_count = result["daily_value_count"]
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
