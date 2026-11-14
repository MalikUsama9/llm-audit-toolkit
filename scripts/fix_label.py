import sqlite3
con = sqlite3.connect("data/audit.db")
con.execute("UPDATE human_labels SET label='partially_correct', note=? WHERE case_id='add-006'",
            ("relabeled: omits the $19.95 amount, judge was right",))
con.commit()
print(con.execute("SELECT case_id, label FROM human_labels WHERE case_id='add-006'").fetchall())