"""test_report.py - find the real audit DB, pick a run, build a test PDF.

Usage (from the project root):
    python test_report.py
    python test_report.py --db data/audit.db
    python test_report.py --db data/audit.db --run-id my_run --out test_report.pdf
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

from audit.reporting.pdf import build_report

SKIP_DIRS = {".venv", "venv", ".git", "__pycache__", "node_modules", ".pytest_cache"}
DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def open_readonly(path: Path) -> sqlite3.Connection:
    # mode=ro means this can never create or modify a database file
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def inspect_db(path: Path):
    """Return (tables, run_ids newest-first), or None if it isn't a readable SQLite file."""
    try:
        conn = open_readonly(path)
    except sqlite3.Error:
        return None
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        run_ids = []
        if "runs" in tables:
            cols = [c[1] for c in conn.execute('PRAGMA table_info("runs")')]
            order = "created_at DESC" if "created_at" in cols else "rowid DESC"
            run_ids = [r[0] for r in conn.execute(
                f"SELECT run_id FROM runs ORDER BY {order}")]
        return tables, run_ids
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def find_db_files(root: Path):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in DB_SUFFIXES:
                found.append(Path(dirpath) / name)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="path to the SQLite file (skips auto-search)")
    ap.add_argument("--run-id", help="run_id to report on (default: newest run)")
    ap.add_argument("--out", default="test_report.pdf")
    args = ap.parse_args()

    candidates = [Path(args.db)] if args.db else find_db_files(Path.cwd())
    if not candidates:
        sys.exit("No .db/.sqlite files found under this folder. "
                 "Run from the project root, or pass --db PATH.")

    usable = []  # (db_path, run_ids)
    print("Database files found:")
    for p in candidates:
        if not p.exists():
            print(f"  {p}  -> does not exist")
            continue
        size = p.stat().st_size
        info = inspect_db(p)
        if info is None:
            print(f"  {p}  ({size} bytes) -> not a readable SQLite file")
            continue
        tables, run_ids = info
        print(f"  {p}  ({size} bytes) tables={tables or 'NONE (empty file)'} "
              f"runs={len(run_ids)}")
        if run_ids:
            usable.append((p, run_ids))

    if not usable:
        sys.exit(
            "\nNo database contains a populated 'runs' table.\n"
            "- 0-byte files with no tables were created by accident; delete them.\n"
            "- If your real DB lists tables but none called 'runs', send me that "
            "list (your store.py may use another name).\n"
            "- If 'runs' exists with 0 rows, run an audit first so a run is saved.")

    # newest-modified DB wins if several qualify
    db_path, run_ids = max(usable, key=lambda x: x[0].stat().st_mtime)
    run_id = args.run_id or run_ids[0]
    if run_id not in run_ids:
        sys.exit(f"run_id '{run_id}' not found in {db_path}. Available: {run_ids}")

    print(f"\nUsing db={db_path}  run_id={run_id}")
    build_report(str(db_path), run_id, args.out)

    out = Path(args.out)
    if out.exists() and out.stat().st_size > 0:
        print(f"done -> {out} ({out.stat().st_size} bytes)")
    else:
        sys.exit("build_report finished but no PDF was written")


if __name__ == "__main__":
    main()