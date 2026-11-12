import sqlite3, sys, os

path = sys.argv[1] if len(sys.argv) > 1 else "data/audit.db"
if not os.path.exists(path):
    sys.exit(f"Database not found: {path}")

con = sqlite3.connect(path)
tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]

def short(v, n=120):
    s = str(v)
    return s if len(s) <= n else s[:n] + "..."

print("Using:", path)
for t in tables:
    info = list(con.execute(f'PRAGMA table_info("{t}")'))
    n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"\n== {t} ({n} rows)")
    print("  columns:", [(r[1], r[2]) for r in info])

# Last few runs, with long values truncated
if "runs" in tables:
    print("\n== latest runs")
    cur = con.execute('SELECT * FROM runs ORDER BY rowid DESC LIMIT 5')
    names = [d[0] for d in cur.description]
    for row in cur:
        print({k: short(v, 300) for k, v in zip(names, row)})

# Value counts for the score columns, if they exist
if "scores" in tables:
    cols = [r[1] for r in con.execute('PRAGMA table_info("scores")')]
    group = [c for c in ("metric", "value") if c in cols]
    if group:
        print("\n== scores grouped by", group)
        q = f'SELECT {", ".join(group)}, COUNT(*) FROM scores GROUP BY {", ".join(group)}'
        for row in con.execute(q):
            print(" ", row)

# One sample row per table, truncated
for t in tables:
    cur = con.execute(f'SELECT * FROM "{t}" LIMIT 1')
    names = [d[0] for d in cur.description]
    row = cur.fetchone()
    if row:
        print(f"\n== sample row from {t}")
        for k, v in zip(names, row):
            print(f"  {k}: {short(v)}")