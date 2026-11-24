import sqlite3
con = sqlite3.connect("data/audit.db")
for rid in ("run_20261117_110249_a29a22", "run_20261118_021953_c80e1b"):
    a = con.execute("SELECT answer FROM results WHERE run_id=? AND case_id='add-008'", (rid,)).fetchone()
    s = con.execute("SELECT metric, value FROM scores WHERE run_id=? AND case_id='add-008'", (rid,)).fetchall()
    print(rid)
    print("ANSWER:", (a[0] or "")[:400])
    print("SCORES:", s, "\n")