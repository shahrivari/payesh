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
