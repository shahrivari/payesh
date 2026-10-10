# Repository Guidelines

## Project Structure & Module Organization

This Python 3.14+ package uses a `src` layout. In `src/payesh/`, `ifb.py` handles source fetching, `database.py` manages announcement storage, `extraction.py` parses PDFs, and `service.py` shares collection logic between the CLI and web app. `web.py` defines the FastAPI endpoints; `web_storage.py` provides dashboard queries and run history. The Persian RTL frontend lives in `static/`. Tests are in `tests/`; runtime databases belong in `data/`. `pyproject.toml` and `uv.lock` define the environment.

## Build, Test, and Development Commands

- `uv sync` installs the project and its locked dependencies.
- `uv run python -m payesh` fetches announcements, stores them and their PDFs in the default SQLite database, and extracts supported PDF data.
- `uv run python -m payesh --db /path/to/file.sqlite3` selects another database; `--format csv` or `--format json` also emits fetched rows in the chosen format.
- `uv build` builds distributable package artifacts.
- `uv run payesh-web` serves the local dashboard and API at `127.0.0.1:8000`.
- `uv run pytest -q` runs the offline test suite.

No formatter or linter is configured. Use `uv run` for project tools.

## Coding Style & Naming Conventions

Use idiomatic Python, four spaces for indentation, and type annotations for public functions and non-obvious data structures. Follow the existing module boundaries and use `snake_case` for modules, functions, and variables; use `PascalCase` for classes. Keep database changes parameterized and preserve the existing separation between announcement metadata, file data, and extracted values.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. API tests use FastAPI TestClient, temporary SQLite databases, and mocked collection sources. Cover query validation, PDF responses, monetary precision, and collection failures or interruption. Avoid live IFB requests in unit tests; use representative local fixtures. No coverage threshold is set.

## Commit & Pull Request Guidelines

The project Git workflow is TBD. Commits use the Conventional Commits format, with a type prefix and concise summary (for example, `feat: extract IFB announcement data from N-suffixed PDFs`). Use `feat:`, `fix:`, or another clear type. Pull requests should explain user-visible changes, include relevant command or test results, and note database/schema changes or configuration requirements.

## Configuration & Data

Pass `--url` to target a different announcements page and `--db` to control database location. Do not commit downloaded PDFs, generated databases, credentials, or other runtime data.
