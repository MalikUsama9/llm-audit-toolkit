import sqlite3, sys

run_a, run_b = sys.argv[1], sys.argv[2]
con = sqlite3.connect("data/audit.db")
rows = con.execute(
    "SELECT a.case_id, a.answer, b.answer FROM results a JOIN results b "
    "ON a.case_id=b.case_id WHERE a.run_id=? AND b.run_id=?",
    (run_a, run_b),
).fetchall()
diff = sum(1 for _, x, y in rows if (x or "").strip() != (y or "").strip())
print(f"compared={len(rows)} different={diff}")
for cid, x, y in rows[:3]:
    print("\nCASE", cid, "\nV1:", (x or "")[:200], "\nV2:", (y or "")[:200])