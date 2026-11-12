import sqlite3

con = sqlite3.connect("data/audit.db")
for r in con.execute("select run_id, target_name, created_at, notes from runs order by created_at"):
    print(r)