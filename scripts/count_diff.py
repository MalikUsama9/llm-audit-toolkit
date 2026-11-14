import sqlite3, sys
a, b = sys.argv[1], sys.argv[2]
c = sqlite3.connect("data/audit.db")
row = c.execute("""
    SELECT COUNT(*), SUM(r1.answer <> r2.answer)
    FROM results r1 JOIN results r2 ON r1.case_id = r2.case_id
    WHERE r1.run_id = ? AND r2.run_id = ?
""", (a, b)).fetchone()
print("overlap, different =", row)