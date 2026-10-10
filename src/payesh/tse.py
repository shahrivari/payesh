"""First-page TSE announcements selected by title, with PDF and Excel attachments."""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlsplit

import jdatetime

from payesh.database import _ensure_schema
from payesh import web_storage as store

API_URL = "https://webgw.tse.ir/cmssite/api/v1/Notice/SimpleList/fa"
PAGE_SIZE = 20


def normalize_title(title: str) -> str:
    title = unicodedata.normalize("NFKC", title).replace("ي", "ی").replace("ك", "ک")
    title = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", title)
    return " ".join(title.split())


def matches_title(title: str) -> bool:
    title = normalize_title(title)
    return "اوراق" in title and ("پذیره" in title or "گشایش" in title)


@dataclass(frozen=True)
class TseAnnouncement:
    source_id: str
    title: str
    published_at: str
    published_at_source: str
    abstract: str
    symbol: str
    attachments: list[dict]
    metadata: dict

    @property
    def notice_number(self) -> str:
        return f"tse:{self.source_id}"


def parse_announcements(payload: dict) -> list[TseAnnouncement]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("TSE response must contain an items array.")
    results = []
    for item in payload["items"]:
        title = item.get("title", "")
        if not matches_title(title):
            continue
        content = item["content"]
        source_id = str(content["id"])
        if not source_id.isdigit():
            raise ValueError("TSE returned an invalid announcement identifier.")
        original_date = content.get("publishAt") or ""
        published = ""
        if original_date:
            timestamp = datetime.fromisoformat(original_date)
            jalali = jdatetime.date.fromgregorian(date=timestamp.date())
            published = f"{timestamp:%H:%M:%S} {jalali.year:04d}/{jalali.month:02d}/{jalali.day:02d}"
        attachments = []
        for file in content.get("files") or []:
            if file.get("isMasterImage"):
                continue
            filename = (file.get("fileName") or "").replace("\\", "/").rsplit("/", 1)[-1]
            extension = Path(filename).suffix.lower()
            if extension not in {".pdf", ".xlsx", ".xls"}:
                continue
            attachments.append({"source_file_id": str(file["fileId"]), "filename": filename,
                                "file_url": file["link"], "kind": "pdf" if extension == ".pdf" else "excel"})
        text = normalize_title(title + " " + (item.get("abstract") or ""))
        symbols = re.findall(r"نماد(?:\s*معاملاتی)?\s*[:：]?\s*[«\"(]([^»\")]+)", text)
        results.append(TseAnnouncement(source_id, title, published, original_date,
                                       item.get("abstract") or "", symbols[0].strip() if symbols else "",
                                       attachments, item))
    return results


def fetch_announcements(timeout: float = 45) -> list[TseAnnouncement]:
    """Fetch exactly page 1; do not follow hasNextPage or totalPages."""
    params = urlencode({"CategoryId": "announcement", "PageNumber": 1, "PageSize": PAGE_SIZE,
                        "SerachText": "", "TagNames": "", "FromDate": "", "ToDate": ""})
    request = urllib.request.Request(API_URL + "?" + params,
                                     headers={"Accept": "application/json", "User-Agent": "Payesh/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, ValueError) as exc:
        raise RuntimeError(f"Could not fetch TSE announcements: {exc}") from exc
    return parse_announcements(payload)


def save_announcements(records: list[TseAnnouncement], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with store.connection(path) as db:
        _ensure_schema(db)
        timestamp = store.now()
        for row, item in enumerate(records, 1):
            link = f"https://www.tse.ir/news/details/{item.source_id}"
            db.execute("""INSERT INTO announcements
                (notice_number,row_number,symbol,title,published_at,file_url,first_seen_at,last_seen_at,
                 source,source_id,source_calendar,published_at_source,abstract,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,'tse',?,'gregorian',?,?,?)
                ON CONFLICT(notice_number) DO UPDATE SET
                    symbol=excluded.symbol,title=excluded.title,published_at=excluded.published_at,
                    last_seen_at=excluded.last_seen_at,published_at_source=excluded.published_at_source,
                    abstract=excluded.abstract,metadata_json=excluded.metadata_json""",
                       (item.notice_number, str(row), item.symbol, item.title, item.published_at, link,
                        timestamp, timestamp, item.source_id, item.published_at_source, item.abstract,
                        json.dumps(item.metadata, ensure_ascii=False)))
            for file in item.attachments:
                db.execute("""INSERT INTO source_attachments
                    (notice_number,source_file_id,filename,file_url,kind) VALUES (?,?,?,?,?)
                    ON CONFLICT(notice_number,source_file_id) DO UPDATE SET
                        filename=excluded.filename,file_url=excluded.file_url,kind=excluded.kind""",
                           (item.notice_number, file["source_file_id"], file["filename"], file["file_url"], file["kind"]))


def missing_attachments(path: Path) -> list[dict]:
    with store.connection(path) as db:
        return [dict(row) for row in db.execute("""SELECT f.* FROM source_attachments f
            JOIN announcements a USING(notice_number) WHERE a.source='tse' AND f.file_blob IS NULL
            ORDER BY f.attachment_id""")]


def download_attachment(file: dict, timeout: float = 60) -> tuple[bytes, str]:
    allowed = {"webgw.tse.ir", "www.tse.ir", "tse.ir"}
    if urlsplit(file["file_url"]).hostname not in allowed:
        raise ValueError("Unexpected TSE attachment host.")
    request = urllib.request.Request(file["file_url"], headers={"User-Agent": "Payesh/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if urlsplit(response.geturl()).hostname not in allowed:
                raise ValueError("Unexpected TSE attachment redirect.")
            content = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download TSE attachment: {exc}") from exc
    if file["kind"] == "pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("TSE attachment was not a PDF.")
        mime = "application/pdf"
    elif Path(file["filename"]).suffix.lower() == ".xls":
        if not content.startswith(b"\xd0\xcf\x11\xe0"):
            raise ValueError("TSE attachment was not an XLS workbook.")
        mime = "application/vnd.ms-excel"
    else:
        if not content.startswith(b"PK"):
            raise ValueError("TSE attachment was not an XLSX workbook.")
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return content, mime


def save_attachment(path: Path, attachment_id: int, content: bytes, mime: str) -> None:
    with store.connection(path) as db:
        db.execute("UPDATE source_attachments SET file_blob=?,content_type=?,downloaded_at=? WHERE attachment_id=?",
                   (content, mime, store.now(), attachment_id))
