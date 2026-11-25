"""Build a small demo database from your real audit database.

The demo database holds ONLY the runs you choose (and the cases they use), so
you can keep client runs out of it. After building, the script scans the new
file for things that should never be public (client names, personal paths,
real email addresses, API keys) and reports every hit.

Step 1: see what is in your database
    python scripts/build_demo_db.py list --source data/audit.db

Step 2: build the demo database from the fictional runs
    python scripts/build_demo_db.py build --source data/audit.db \
        --out data/demo/demo.db --runs RUN_ID_1 RUN_ID_2 \
        --forbid "Client Name" "other private word"

Step 3: re-check any database at any time
    python scripts/build_demo_db.py scan --db data/demo/demo.db --forbid "Client Name"
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

# Reserved example domains (never real people) are allowed in the demo.
SAFE_EMAIL_SUFFIXES = (".example", "example.com", "example.org", "example.net")

PATTERNS = {
    "windows user path": re.compile(r"[A-Za-z]:\\+Users\\+", re.I),
    "unix home path": re.compile(r"(?:/home/|/Users/)[\w.-]+"),
    "clients folder": re.compile(r"data[/\\]+clients", re.I),
    "API key": re.compile(r"sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}"),
}
EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


def connect_readonly(path):
    if not Path(path).exists():
        sys.exit(f"File not found: {path}")
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def tables(con):
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def columns(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def run_id_col(con):
    cols = columns(con, "runs")
    for c in ("run_id", "id"):
        if c in cols:
            return c
    sys.exit("The runs table has no run_id or id column.")


# ------------------------------------------------------------------ list
def cmd_list(args):
    con = connect_readonly(args.source)
    rid = run_id_col(con)
    cols = columns(con, "runs")
    snap = next((c for c in cols if "snapshot" in c or "config" in c), None)
    print(f"Runs in {args.source}  (newest first)\n")
    for (run,) in con.execute(f"SELECT {rid} FROM runs ORDER BY rowid DESC").fetchall():
        n_res = con.execute("SELECT COUNT(*) FROM results WHERE run_id=?", (run,)).fetchone()[0]
        n_sc = con.execute("SELECT COUNT(DISTINCT case_id) FROM scores WHERE run_id=?", (run,)).fetchone()[0]
        try:
            q = con.execute(
                "SELECT c.question FROM results r JOIN cases c ON c.id = r.case_id "
                "WHERE r.run_id=? LIMIT 1", (run,)).fetchone()
            sample = (q[0] or "")[:70] if q else ""
        except sqlite3.Error:
            sample = ""
        config = ""
        if snap:
            row = con.execute(f"SELECT {snap} FROM runs WHERE {rid}=?", (run,)).fetchone()
            config = (row[0] or "")[:90] if row else ""
        print(f"{run}\n    answers: {n_res}   scored cases: {n_sc}")
        print(f"    first question: {sample}")
        if config:
            print(f"    config: {config}")
    print(
        "\nPick the runs that use ONLY fictional demo documents, then run:\n"
        "    python scripts/build_demo_db.py <baseline_run_id> <after_run_id>"
    )


# ------------------------------------------------------------------ scan
def scan_db(path, forbid):
    con = connect_readonly(path)
    forbid = [f.lower() for f in forbid if f.strip()]
    hits = []
    for t in tables(con):
        cols = columns(con, t)
        for row in con.execute(f'SELECT rowid, * FROM "{t}"'):
            rowid, values = row[0], row[1:]
            for col, val in zip(cols, values):
                if not isinstance(val, str):
                    continue
                low = val.lower()
                for term in forbid:
                    if term in low:
                        hits.append((t, col, rowid, f"forbidden term '{term}'"))
                for label, pat in PATTERNS.items():
                    if pat.search(val):
                        hits.append((t, col, rowid, label))
                for m in EMAIL.finditer(val):
                    domain = m.group(1).lower()
                    if not domain.endswith(SAFE_EMAIL_SUFFIXES):
                        hits.append((t, col, rowid, f"real-looking email {m.group(0)}"))
    return hits


def report_hits(hits):
    if not hits:
        print("Privacy scan: no client names, personal paths, real emails or API keys found.")
        return
    print(f"Privacy scan: {len(hits)} possible problem(s). Review before sharing this file:")
    for t, col, rowid, why in hits[:25]:
        print(f"  - table {t}, column {col}, row {rowid}: {why}")
    if len(hits) > 25:
        print(f"  ... and {len(hits) - 25} more")


def cmd_scan(args):
    hits = scan_db(args.db, args.forbid)
    report_hits(hits)
    sys.exit(1 if hits else 0)


# ------------------------------------------------------------------ redact
def redact_paths(con):
    """Replace personal home-directory paths so a rebuild never leaks them."""
    win = re.compile(r'[A-Za-z]:\\+Users\\+[^\\"]+')
    nix = re.compile(r"(?:/home/|/Users/)[\w.-]+")
    for t in tables(con):
        cols = columns(con, t)
        for rowid, *vals in con.execute(f'SELECT rowid, * FROM "{t}"').fetchall():
            for col, val in zip(cols, vals):
                if isinstance(val, str):
                    new = nix.sub("~", win.sub("~", val))
                    if new != val:
                        con.execute(f'UPDATE "{t}" SET "{col}"=? WHERE rowid=?', (new, rowid))


# ------------------------------------------------------------------ build
def cmd_build(args):
    src_path, out_path = Path(args.source).resolve(), Path(args.out).resolve()
    if src_path == out_path:
        sys.exit("--out must be a different file from --source.")
    src = connect_readonly(args.source)
    rid = run_id_col(src)

    known = {r[0] for r in src.execute(f"SELECT {rid} FROM runs")}
    missing = [r for r in args.runs if r not in known]
    if missing:
        sys.exit("These run ids are not in the source database: " + ", ".join(missing))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    out = sqlite3.connect(out_path)

    # same tables and indexes as the source
    for name, sql in src.execute(
            "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL "
            "AND name NOT LIKE 'sqlite_%' ORDER BY type = 'table' DESC"):
        out.execute(sql)

    marks = ",".join("?" * len(args.runs))
    skipped = []
    for t in tables(src):
        cols = columns(src, t)
        if t == "runs":
            sql, params = f"SELECT * FROM runs WHERE {rid} IN ({marks})", args.runs
        elif "run_id" in cols:
            sql, params = f'SELECT * FROM "{t}" WHERE run_id IN ({marks})', args.runs
        elif t == "cases":
            sql = (f"SELECT * FROM cases WHERE id IN ("
                   f"SELECT case_id FROM results WHERE run_id IN ({marks}) "
                   f"UNION SELECT case_id FROM scores WHERE run_id IN ({marks}))")
            params = args.runs + args.runs
        else:
            skipped.append(t)
            continue
        rows = src.execute(sql, params).fetchall()
        if rows:
            q = ",".join("?" * len(cols))
            out.executemany(f'INSERT INTO "{t}" VALUES ({q})', rows)
    redact_paths(out)
    out.commit()
    out.execute("VACUUM")
    out.close()

    print(f"Built {args.out}\n")
    check = sqlite3.connect(out_path)
    for t in tables(check):
        n = check.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t:<14}{n:>6} rows")
    scored = check.execute("SELECT COUNT(DISTINCT run_id) FROM scores").fetchone()[0]
    check.close()
    print(f"\n  scored runs in the demo database: {scored}")
    if skipped:
        print("  tables NOT copied (no run_id, so they could hold other data): "
              + ", ".join(skipped))

    print()
    hits = scan_db(out_path, args.forbid)
    report_hits(hits)
    if hits:
        print("\nThe file was created, but do NOT publish it until these are fixed.")
        sys.exit(1)
    print("\nNext: open the dashboard and check that it loads data/demo/demo.db cleanly.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("list", help="show the runs in a database")
    a.add_argument("--source", default="data/audit.db")
    a.set_defaults(func=cmd_list)

    b = sub.add_parser("build", help="copy chosen runs into a new demo database")
    b.add_argument("--source", default="data/audit.db")
    b.add_argument("--out", default="data/demo/demo.db")
    b.add_argument("--runs", nargs="+", required=True)
    b.add_argument("--forbid", nargs="*", default=[],
                   help="words that must not appear (client names etc.)")
    b.set_defaults(func=cmd_build)

    c = sub.add_parser("scan", help="privacy-scan an existing database")
    c.add_argument("--db", default="data/demo/demo.db")
    c.add_argument("--forbid", nargs="*", default=[])
    c.set_defaults(func=cmd_scan)

    args = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args.func(args)


if __name__ == "__main__":
    main()