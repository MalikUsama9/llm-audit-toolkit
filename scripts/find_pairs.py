import sqlite3
from itertools import combinations

con = sqlite3.connect("data/audit.db")
runs = [r[0] for r in con.execute("SELECT run_id FROM runs ORDER BY created_at")]
print(f"{'run A':32} {'run B':32} overlap  different")
rows = []
for a, b in combinations(runs, 2):
    overlap, diff = con.execute("""
        SELECT COUNT(*), SUM(r1.answer <> r2.answer)
        FROM results r1 JOIN results r2 ON r1.case_id = r2.case_id
        WHERE r1.run_id = ? AND r2.run_id = ?
          AND coalesce(trim(r1.answer),'') <> '' AND coalesce(trim(r2.answer),'') <> ''
          AND r1.error IS NULL AND r2.error IS NULL""", (a, b)).fetchone()
    rows.append((diff or 0, overlap, a, b))
for diff, overlap, a, b in sorted(rows, reverse=True)[:10]:
    print(f"{a:32} {b:32} {overlap:7} {diff:9}")