# Payesh

A Python application for monitoring and collecting data from web sources.

## Requirements

- Python 3.14 or newer
- uv

## Development setup

```bash
uv sync
```

## Fetch and store IFB announcements

Fetch the announcements table, upsert the rows, download their PDFs, and store announcement metadata and file data in separate SQLite tables in `data/payesh.sqlite3`:

```bash
uv run python -m payesh
```

The `announcements` table uses the notice number as its key. PDF filenames, content types, BLOBs, and download timestamps live in the related `announcement_files` table. Re-fetching the page updates existing rows, adds new announcements, and downloads PDFs only for rows that do not already have a stored file. Each run prints a report with record counts, stored PDF bytes, and any download failures. To use another database file:

PDFs whose filename ends in `N.pdf` are parsed with `pypdf`. Best-effort extracted fields are stored as JSON in `announcement_extractions`; daily interest rows are stored separately in `daily_interest_values`. The extraction status identifies complete, partial, unrecognized, or text-free documents.

```bash
uv run python -m payesh --db /path/to/announcements.sqlite3
```

To also print the fetched rows as CSV or JSON:

```bash
uv run python -m payesh --format csv
uv run python -m payesh --format json
```

The collector reads the announcements table currently returned by the IFB page. It does not yet traverse the page numbers or submit date and symbol filters.

Application code lives in `src/payesh/`.

## Local web dashboard and REST API

Start the Persian, right-to-left dashboard:

```bash
uv sync
uv run payesh-web
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The dashboard uses your existing
`data/payesh.sqlite3` database. Search and filter stored announcements, inspect
extracted fields and daily interest values, view or download PDFs, and use
«دریافت اطلاعیه‌ها» to collect new data. An empty database starts with an empty
dashboard; the UI never supplies sample records.

```bash
uv run payesh-web --db /path/to/announcements.sqlite3 --port 8001
```

The server binds to `127.0.0.1` and is intended for one local process. It has no
login. Collection runs in the background, persists progress and errors in
`collection_runs`, and rejects overlapping web collection requests. A restart
marks an unfinished run as interrupted; the next collection retries missing
PDFs. Run collection through the dashboard or CLI one at a time. The current
collector still reads only the IFB page returned by the source, without following
source pagination. Read requests never initiate collection.

Interactive API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/announcements` | Paginated announcements; `page`, `page_size`, `q`, `symbol`, `status`, `document_type`, `date_from`, `date_to` |
| `GET /api/v1/announcements/{notice_number}` | Metadata, extraction fields, and daily interest values |
| `GET /api/v1/announcements/{notice_number}/pdf` | Inline stored PDF; `?download=true` downloads it |
| `GET /api/v1/stats` | Counts, storage size, and latest collection run |
| `POST /api/v1/collection-runs` | Start collection, returning HTTP 202 and a run ID; HTTP 409 if busy |
| `GET /api/v1/collection-runs` | Most recent 20 runs |
| `GET /api/v1/collection-runs/{run_id}` | Run progress, result, and failures |

Date filters use zero-padded `YYYY-MM-DD` or `YYYY/MM/DD` in the source calendar
(normally Jalali), with Persian or Latin digits. Dates are normalized for
comparison without calendar conversion. Monetary values remain strings to
preserve precision, and are labeled in rials. Run timestamps are stored in UTC
and displayed in Tehran time. The UI font uses Google Fonts with a system-font
fallback; all application logic and data run locally.

## Tests

```bash
uv run pytest -q
```

Tests use temporary SQLite databases and mocked collection sources. They do not
make live IFB requests.
