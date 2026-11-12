import re, sqlite3
from src.audit.checks import REFUSAL_PATTERNS, run_checks

conn = sqlite3.connect("data/audit.db")
rows = [r[0] for r in conn.execute("SELECT answer FROM results WHERE answer LIKE 'Whether you have to pay for return shipping%'")]
conn.close()

a = rows[0]
print(a, "\n")
for p in REFUSAL_PATTERNS:
    m = re.search(p, a.replace("\u2019", "'"), re.I | re.S)
    if m:
        print("MATCHED:", p)
        print("TEXT   :", m.group(0))
