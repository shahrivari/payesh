"""Shared startup options for storage and scheduled collection."""

import argparse
import math
import os
from pathlib import Path


def minutes(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Interval must be a number of minutes.") from exc
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("Interval must be finite and nonnegative; 0 disables updates.")
    return result


def add_storage_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--db", type=Path, help="Explicit SQLite database path.")
    group.add_argument("--data-dir", type=Path, help="Data directory (default: PAYESH_DATA_DIR or ./data).")


def database_path(args) -> Path:
    if args.db is not None:
        return args.db.expanduser()
    directory = args.data_dir or Path(os.environ.get("PAYESH_DATA_DIR", "data"))
    return directory.expanduser() / "payesh.sqlite3"
