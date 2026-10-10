# Payesh

A Python application for monitoring and collecting data from web sources.

## Requirements

- Python 3.14 or newer
- uv

## Development setup

```bash
uv sync
```

## Fetch and store announcements

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

The collector reads the current IFB table and only the newest TSE announcement page (`PageNumber=1`, `PageSize=20`). It never scans the archive or follows pagination. TSE titles must contain both «پذیره» and «اوراق», or both «گشایش» and «اوراق», after Persian text normalization. All PDF and Excel (`.xlsx`, `.xls`) attachments on matching announcements are eligible, regardless of filename; images are excluded. TSE attachment metadata and bytes live in `source_attachments`, with source IDs namespaced to avoid IFB collisions.

TSE PDFs use best-effort extraction; Excel extraction reads cached values and supported date/interest columns without recalculating formulas. Missing values and unsupported layouts remain partial or unrecognized.

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

Automatic collection runs every hour while this server stays running, beginning
one hour after startup. It appends unseen notice numbers and updates existing
ones without duplicates, using the same collector as the manual button. Missing
attachments are retried. Scheduled runs appear in collection history with
`started_by: "scheduled"`; manual runs use `"manual"`. The dashboard displays the
next automatic update in Tehran time. Closing the browser does not stop updates;
stopping the server or shutting down the computer does. Each server restart
starts a new hourly interval. If a manual run is active at a scheduled tick,
that tick is skipped to prevent overlapping collection.

To run only manual updates:

```bash
uv run payesh-web --no-auto-update
```

```bash
uv run payesh-web --db /path/to/announcements.sqlite3 --port 8001
```

The server binds to `127.0.0.1` and is intended for one local process. It has no
login. Collection runs in the background, persists progress and errors in
`collection_runs`, and rejects overlapping web collection requests. A restart
marks an unfinished run as interrupted; the next collection retries missing
PDFs. Run collection through the dashboard or CLI one at a time. The current
collector reads the current IFB page and newest TSE page, without following
source pagination. Read requests never initiate collection.

Interactive API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/announcements` | Paginated announcements; `page`, `page_size`, `q`, `source` (`ifb` or `tse`), `symbol`, `status`, `document_type`, `date_from`, `date_to` |
| `GET /api/v1/announcements/{notice_number}` | Metadata, extraction fields, and daily interest values |
| `GET /api/v1/announcements/{notice_number}/pdf` | Inline stored PDF; `?download=true` downloads it |
| `GET /api/v1/announcements/{notice_number}/attachments/{attachment_id}` | Stored TSE PDF or Excel; `?download=true` forces download |
| `GET /api/v1/stats` | Counts, storage size, and latest collection run |
| `POST /api/v1/collection-runs` | Start collection, returning HTTP 202 and a run ID; HTTP 409 if busy |
| `GET /api/v1/collection-runs` | Most recent 20 runs |
| `GET /api/v1/collection-runs/{run_id}` | Run progress, result, and failures |

Date filters use zero-padded `YYYY-MM-DD` or `YYYY/MM/DD` in the Jalali calendar, with Persian or Latin digits. TSE Gregorian publication dates are converted to Jalali for comparison and display; original timestamps and source calendar are retained. Monetary values remain strings to
preserve precision, and are labeled in rials. Run timestamps are stored in UTC
and displayed in Tehran time. The UI font uses Google Fonts with a system-font
fallback; all application logic and data run locally.

## Tests

```bash
uv run pytest -q
```

Tests use temporary SQLite databases and mocked collection sources. They do not
make live source requests.
