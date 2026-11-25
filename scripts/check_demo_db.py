import sqlite3

con = sqlite3.connect("data/demo/demo.db")
tables = [t for (t,) in con.execute("select name from sqlite_master where type='table'")]

# Check 1: secrets
for pat in ["AIza", "gsk_", "sk-", "Bearer "]:
    for t in tables:
        for row in con.execute(f"select * from {t}"):
            if any(pat in str(c) for c in row):
                print("FOUND", pat, "in", t)
                break
print("secret scan done")

# Check 2: personal paths and URLs
for pat in ["C:\\Users", "/Users/", "/home/", "http://", "https://"]:
    for t in tables:
        for row in con.execute(f"select * from {t}"):
            if any(pat in str(c) for c in row):
                print("FOUND", pat, "in", t)
                break
print("path/url scan done")

# Check 3: look at the runs rows
print()
cols = [c[1] for c in con.execute("pragma table_info(runs)")]
print("runs columns:", cols)
for r in con.execute("select * from runs"):
    print(r)