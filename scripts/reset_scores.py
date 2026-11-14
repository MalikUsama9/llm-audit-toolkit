import sqlite3
con = sqlite3.connect("data/audit.db")
con.execute("DELETE FROM scores WHERE EXISTS (SELECT 1 FROM human_labels h WHERE h.run_id = scores.run_id AND h.case_id = scores.case_id)")
con.commit()
print("remaining scores:", con.execute("SELECT COUNT(*) FROM scores").fetchone()[0])