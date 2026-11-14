import sqlite3, sys
c = sqlite3.connect("data/audit.db")
n = c.execute("DELETE FROM pairwise_judgments WHERE run_a=? AND run_b=?", (sys.argv[1], sys.argv[2])).rowcount
c.commit()
print("deleted rows:", n)