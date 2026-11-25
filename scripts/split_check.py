import sqlite3
from audit.reporting.summary import build_summary

DB = "data/audit.db"
BASE = "run_20261117_110249_a29a22"
con = sqlite3.connect(DB)
s = build_summary(DB, BASE, top_n=100)

dev, held = [], []
for f in s["failures"]:
    split = con.execute("SELECT split FROM cases WHERE id=?", (f["case_id"],)).fetchone()[0]
    (held if split == "heldout" else dev).append((f["case_id"], f["category"]))

print("DEV failures (allowed to guide fixes):")
for c in dev: print("  ", c)
print("\nHELD-OUT failures (must NOT guide fixes):")
for c in held: print("  ", c)