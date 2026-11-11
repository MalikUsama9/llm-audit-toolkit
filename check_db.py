# check_db.py
import sqlite3

DB = "data/audit.db"
con = sqlite3.connect(DB)
cur = con.cursor()

tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
print("Tables:", tables)

for t in tables:
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({t})")]
    print(f"\n[{t}] {n} rows")
    print("  columns:", cols)

    # heuristic health checks on whichever table holds the bot answers
    ans_cols = [c for c in cols if "answer" in c.lower()]
    err_cols = [c for c in cols if "error" in c.lower()]
    if ans_cols:
        a = ans_cols[0]
        empty = cur.execute(
            f"SELECT COUNT(*) FROM {t} WHERE {a} IS NULL OR TRIM({a}) = ''").fetchone()[0]
        print(f"  empty answers ({a}): {empty}")
    if err_cols:
        e = err_cols[0]
        errs = cur.execute(
            f"SELECT COUNT(*) FROM {t} WHERE {e} IS NOT NULL AND TRIM({e}) <> ''").fetchone()[0]
        print(f"  rows with error ({e}): {errs}")

con.close()