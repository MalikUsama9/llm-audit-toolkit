import sqlite3
con = sqlite3.connect("data/audit.db")
con.execute("""UPDATE cases SET expected_behavior='answer',
    reference_answer='No. Tidewell Home is online only and has no physical stores.'
    WHERE id='human-21'""")
con.commit()
print(con.execute("SELECT id, expected_behavior FROM cases WHERE id='human-21'").fetchall())