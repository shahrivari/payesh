"""Fetch and parse the announcements table from Iran Fara Bourse."""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

ANNOUNCEMENTS_URL = "https://ifb.ir/anouncments.aspx"
ANNOUNCEMENTS_TABLE_ID = "ContentPlaceHolder1_grdAnouncments"
USER_AGENT = "Payesh/0.1 (+https://ifb.ir/)"


@dataclass(frozen=True, slots=True)
class Announcement:
    """One row from the IFB announcements table."""

    row_number: str
    symbol: str
    notice_number: str
    title: str
    published_at: str
    file_url: str


@dataclass(frozen=True, slots=True)
class PdfDocument:
    """A downloaded announcement PDF."""

    filename: str
    content: bytes
    content_type: str


def _clean_text(value: str) -> str:
    """Normalize whitespace and remove invisible bidirectional controls."""
    value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", value)
    return " ".join(value.split())


def parse_announcements(html: str, page_url: str = ANNOUNCEMENTS_URL) -> list[Announcement]:
    """Parse announcement rows from an IFB announcements page response."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=ANNOUNCEMENTS_TABLE_ID)
    if table is None:
        raise ValueError(f"Could not find the announcements table ({ANNOUNCEMENTS_TABLE_ID}).")

    announcements: list[Announcement] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 5:
            continue

        values = [_clean_text(cell.get_text(" ", strip=True)) for cell in cells[:5]]
        if values[0] == "ردیف":
            continue

        title_cell = cells[3]
        title_link = title_cell.find("a", href=True)
        if title_link is None or "GetAnnouncmentFile" not in title_link["href"]:
            continue

        title = _clean_text(title_link.get_text(" ", strip=True))
        file_url = urljoin(page_url, title_link["href"])

        announcements.append(
            Announcement(
                row_number=values[0],
                symbol=values[1],
                notice_number=values[2],
                title=title,
                published_at=values[4],
                file_url=file_url,
            )
        )

    return announcements


def fetch_announcements(
    page_url: str = ANNOUNCEMENTS_URL,
    timeout: float = 30,
) -> list[Announcement]:
    """Download the IFB announcements page and return its table rows."""
    request = urllib.request.Request(
        page_url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not fetch {page_url}: {exc}") from exc

    return parse_announcements(html, page_url=page_url)


def download_announcement_pdf(
    file_url: str,
    timeout: float = 60,
) -> PdfDocument:
    """Download one IFB announcement PDF and return its filename and bytes."""
    host = (urlsplit(file_url).hostname or "").lower()
    if host not in {"ifb.ir", "www.ifb.ir"}:
        raise ValueError(f"Refusing to download a PDF from an unexpected host: {host or file_url}")

    request = urllib.request.Request(
        file_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            filename = response.headers.get_filename() or "announcement.pdf"
            content_type = response.headers.get_content_type()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download {file_url}: {exc}") from exc

    if not content.startswith(b"%PDF-"):
        raise ValueError(f"The response from {file_url} was not a PDF file.")

    filename = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    return PdfDocument(filename=filename, content=content, content_type=content_type)


def format_announcements(
    announcements: list[Announcement],
    output_format: Literal["csv", "json"] = "csv",
) -> str:
    """Serialize announcements as CSV or JSON."""
    records = [asdict(announcement) for announcement in announcements]
    if output_format == "json":
        return json.dumps(records, ensure_ascii=False, indent=2)

    output = io.StringIO(newline="")
    fieldnames = list(Announcement.__dataclass_fields__)
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()
