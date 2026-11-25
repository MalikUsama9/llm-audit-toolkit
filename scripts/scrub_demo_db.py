import sqlite3, json

con = sqlite3.connect("data/demo/demo.db")
for run_id, snap in con.execute("select run_id, config_snapshot from runs").fetchall():
    cfg = json.loads(snap)
    if "docs_dir" in cfg:
        cfg["docs_dir"] = "data/demo/docs"
    con.execute("update runs set config_snapshot=? where run_id=?", (json.dumps(cfg), run_id))
con.commit()
con.execute("vacuum")
con.close()

con = sqlite3.connect("data/demo/demo.db")
for (t,) in con.execute("select name from sqlite_master where type='table'").fetchall():
    for row in con.execute(f"select * from {t}"):
        if any(p in str(c) for p in ["Users", "ST\\", "llm-audit-toolkit"] for c in row):
            print("STILL FOUND in", t)
            break
print("scrub done")