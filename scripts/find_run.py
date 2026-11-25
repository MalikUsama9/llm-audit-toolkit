import sqlite3, glob
rid = "run_20261117_110249_a29e22"
for p in glob.glob("**/*.db", recursive=True):
    try:
        n = sqlite3.connect(p).execute("SELECT COUNT(*) FROM runs WHERE run_id=?", (rid,)).fetchone()[0]
        print(p, "->", "HAS RUN" if n else "no")
    except Exception as e:
        print(p, "-> n/a")