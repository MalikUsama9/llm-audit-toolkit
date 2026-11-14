import sqlite3
con = sqlite3.connect("data/audit.db")
con.execute("UPDATE human_labels SET label='partially_correct', note=? WHERE case_id='human-07'",
            ("relabeled: omits that the $49 threshold is after discounts and before tax, judge was right",))
con.commit()
print(con.execute("SELECT case_id, label FROM human_labels WHERE case_id='human-07'").fetchall()) 