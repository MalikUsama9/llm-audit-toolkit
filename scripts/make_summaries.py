import sqlite3, json
from audit.reporting.summary import build_summary

DB = "data/audit.db"
con = sqlite3.connect(DB)

targets = {"110249": "baseline_summary.json", "021953": "after_summary.json"}

for key, out in targets.items():
    rows = con.execute("SELECT run_id FROM runs WHERE run_id LIKE ?", (f"%{key}%",)).fetchall()
    print(key, "->", [repr(r[0]) for r in rows])
    if not rows:
        print("  not found, skipping")
        continue
    rid = rows[0][0]  # exact string as stored in the DB
    s = build_summary(DB, rid, top_n=10)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, default=str)
    print(f"  wrote {out}  judged={s['counts']['judged']} total={s['counts']['total']} errors={s['counts']['errors']}")