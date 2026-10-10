"""Extract structured bond data from IFB announcement PDFs ending in N."""

from __future__ import annotations

import io
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from payesh.database import DEFAULT_DB_PATH, _ensure_schema

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DATE = r"(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})"
_AMOUNT = r"[\d,٬،]+(?:\.\d+)?"
_BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = _BIDI.sub("", value).translate(_DIGITS)
    return value.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("ء", "")


def _first(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip(" \t:؛،,.-") if match else None


def _date_value(value: str | None) -> str | None:
    if not value:
        return None
    parts = [int(part) for part in re.split(r"[/-]", value)]
    if parts[0] < 1000:
        parts = [parts[2], parts[1], parts[0]]
    return f"{parts[0]:04d}/{parts[1]:02d}/{parts[2]:02d}"


def _labeled_date(labels: str, text: str) -> str | None:
    raw = _first(rf"(?:{labels})\s*[:：]?\s*.{{0,45}}?({_DATE})", text)
    return _date_value(raw)


def _extract_daily_values(text: str) -> list[dict[str, str | None]]:
    values: dict[str, str | None] = {}
    for line in text.splitlines():
        match = re.search(rf"({_DATE})\s+(-|{_AMOUNT})\s*$", line.strip())
        if match:
            date = _date_value(match.group(1))
            amount = match.group(2).replace(",", "").replace("٬", "").replace("،", "")
            values[date or match.group(1)] = None if amount == "-" else amount
    return [{"payment_date": date, "amount_rial": amount} for date, amount in values.items()]


def extract_pdf_data(content: bytes) -> tuple[dict[str, Any], list[dict[str, str | None]]]:
    """Return best-effort structured fields and daily interest rows."""
    reader = PdfReader(io.BytesIO(content))
    text = _normalize("\n".join(page.extract_text() or "" for page in reader.pages))
    compact = re.sub(r"[ \t]+", " ", text)

    if re.search(r"سود\s*روز\s*شمار|روز\s*شمار\s*(?:سود|بها)", compact):
        document_type = "daily_interest"
    elif re.search(r"پذیره\s*نویسی|پذیرش\s*(?:اوراق|اسناد)", compact):
        document_type = "subscription"
    else:
        document_type = "unknown"

    quoted_symbol_text = " ".join(re.findall(r"نماد.{0,45}?[«»]([^«»\n]+)[«»]", compact))
    symbols = re.findall(r"[آ-یA-Za-z]+(?:\s+[آ-یA-Za-z]+)?\s*\d+", quoted_symbol_text)
    if not symbols:
        labeled_symbol = _first(r"نماد(?:\s*اوراق)?\s*[:：]\s*([^\s:：]+)", compact)
        if labeled_symbol:
            symbols = [labeled_symbol]
    symbols = list(
        dict.fromkeys(
            re.sub(r"و(?=\d)", "", " ".join(item.split()))
            for item in symbols
        )
    )

    data: dict[str, Any] = {
        "document_type": document_type,
        "instrument_name": _first(
            r"نام\s*و\s*نوع\s*اوراق\s*[:：]?\s*(.+?)(?=\s{2,}|\s+نماد\s*[:：])",
            text,
        ),
        "symbol": symbols[0] if symbols else None,
        "symbols": symbols,
        "issuer": _first(r"نام\s*ناشر\s*[:：]?\s*([^\n]+)", text),
        "market_maker": _first(r"بازارگردان\s*[:：]?\s*([^\n]+)", text),
        "guarantor": _first(r"ضامن\s*[:：]?\s*([^\n]+)", text),
        "profit_formula": _first(r"فرمول\s*محاسبه\s*سود\s*[:：]?\s*([^\n]+)", text),
        "annual_yield_percent": _first(
            rf"(?:نرخ\s*(?:سود|اجاره\s*بها|اجارهبها)(?:\s*اوراق)?|اجاره\s*بها\s*نرخ)\s*[:：]?\s*({_AMOUNT})\s*درصد",
            compact,
        ),
        "repurchase_rate_percent": _first(rf"نرخ\s*بازخرید\s*[:：]?\s*({_AMOUNT})", compact),
        "nominal_value_rial": _first(rf"مبلغ\s*اسمی\s*هر\s*ورقه\s*[:：]?\s*({_AMOUNT})", compact),
        "profit_payment_interval_months": _first(
            r"(?:دوره\s*پرداخت\s*(?:سود|اجاره\s*بها)|پرداخت\s*(?:سود|اجاره\s*بها))\s*[:：]?\s*(\d+)\s*ماه",
            compact,
        ),
        "publication_date": _labeled_date(r"تاریخ\s*انتشار(?:\s*اوراق)?", compact),
        "maturity_date": _labeled_date(r"تاریخ\s*سررسید(?:\s*اوراق)?", compact),
        "subscription_start_date": None,
        "subscription_end_date": None,
        "subscription_period_days": _first(r"به\s*مدت\s*(\S+\s*روز\s*کاری)", compact),
    }

    term_months = _first(r"مدت\s*اوراق\s*[:：]?\s*(\d+)\s*ماه", compact)
    term_years = _first(r"مدت\s*اوراق\s*[:：]?\s*(\d+)\s*سال", compact)
    data["term_months"] = int(term_months) if term_months else (int(term_years) * 12 if term_years else None)
    data["term_years"] = round(data["term_months"] / 12, 4) if data["term_months"] is not None else None

    if data["annual_yield_percent"] is None:
        data["annual_yield_percent"] = _first(rf"({_AMOUNT})\s*درصد\s*سالانه", compact)
    if data["profit_payment_interval_months"] is None:
        data["profit_payment_interval_months"] = _first(r"هر\s*(\d+)\s*ماه\s*یکبار", compact)

    start_context = _first(rf"(?:از\s*روز.{{0,35}}?|پذیره\s*نویسی\s*از\s*تاریخ\s*)({_DATE})", compact)
    data["subscription_start_date"] = _date_value(start_context)
    if data["subscription_start_date"] is None and document_type == "subscription":
        data["subscription_start_date"] = data["publication_date"]

    daily_values = _extract_daily_values(text) if document_type == "daily_interest" else []
    fields = [key for key, value in data.items() if value not in (None, "")]
    data["fields_found"] = fields
    required_fields = (
        ("symbol", "annual_yield_percent", "profit_payment_interval_months", "publication_date", "maturity_date")
        if document_type == "daily_interest"
        else ("symbol", "publication_date", "maturity_date", "nominal_value_rial")
    )
    data["extraction_status"] = (
        "unrecognized" if document_type == "unknown" else
        "complete" if all(data.get(key) for key in required_fields) else "partial"
    )
    if not text.strip():
        data["extraction_status"] = "no_text"
    return data, daily_values


def extract_target_pdfs(db_path: str | Path = DEFAULT_DB_PATH) -> tuple[int, int, int, int]:
    """Extract N-suffixed PDFs and persist fields and daily amounts."""
    path = Path(db_path).expanduser()
    if not path.exists():
        return 0, 0, 0, 0

    with sqlite3.connect(path) as connection:
        _ensure_schema(connection)
        records = connection.execute(
            """SELECT notice_number, filename, file_blob FROM announcement_files
               WHERE upper(filename) LIKE '%N.PDF' ORDER BY filename"""
        ).fetchall()
        processed = partial = daily_rows = 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for notice_number, filename, content in records:
            try:
                data, daily_values = extract_pdf_data(content)
                status = str(data["extraction_status"])
                serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)
                connection.execute(
                    """INSERT INTO announcement_extractions
                       (notice_number, document_type, extraction_status, extracted_data_json, extracted_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(notice_number) DO UPDATE SET
                           document_type=excluded.document_type,
                           extraction_status=excluded.extraction_status,
                           extracted_data_json=excluded.extracted_data_json,
                           extracted_at=excluded.extracted_at""",
                    (notice_number, data["document_type"], status, serialized, now),
                )
                connection.execute("DELETE FROM daily_interest_values WHERE notice_number = ?", (notice_number,))
                connection.executemany(
                    "INSERT INTO daily_interest_values (notice_number, payment_date, amount_rial) VALUES (?, ?, ?)",
                    [(notice_number, item["payment_date"], item["amount_rial"]) for item in daily_values],
                )
                processed += 1
                partial += status != "complete"
                daily_rows += len(daily_values)
            except Exception as exc:
                data = {"document_type": "unknown", "extraction_status": "error", "error": str(exc), "filename": filename}
                connection.execute(
                    """INSERT INTO announcement_extractions
                       (notice_number, document_type, extraction_status, extracted_data_json, extracted_at)
                       VALUES (?, 'unknown', 'error', ?, ?)
                       ON CONFLICT(notice_number) DO UPDATE SET
                           document_type='unknown', extraction_status='error',
                           extracted_data_json=excluded.extracted_data_json,
                           extracted_at=excluded.extracted_at""",
                    (notice_number, json.dumps(data, ensure_ascii=False), now),
                )
                processed += 1
                partial += 1
    return len(records), processed - partial, partial, daily_rows
