import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
tables = [r[0] for r in db.execute("select name from sqlite_master where type='table'")]
print("Tables:", tables)
for t in tables:
    if "run" in t.lower():
        print(f"\n--- {t} ---")
        cur = db.execute(f"select * from {t} order by rowid desc limit 10")
        print([d[0] for d in cur.description])
        for row in cur.fetchall():
            print(row)
