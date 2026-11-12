import sqlite3
from collections import Counter
from src.audit.checks import run_checks

conn = sqlite3.connect("data/audit.db")
rows = conn.execute("""
    SELECT c.expected_behavior, r.answer, r.error
    FROM results r JOIN cases c ON c.id = r.case_id
""").fetchall()
conn.close()

counts = Counter((eb, run_checks(a, bot_error=e).status) for eb, a, e in rows)
for k, v in sorted(counts.items(), key=str):
    print(k, v)
