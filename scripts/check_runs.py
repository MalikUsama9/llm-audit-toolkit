import sqlite3, sys
from audit.reporting.summary import build_summary
db_path = sys.argv[1]
db = sqlite3.connect(db_path)
tables = [r[0] for r in db.execute("select name from sqlite_master where type='table'")]
t = next((x for x in tables if x.lower() in ("runs", "run")), None)
if not t:
    raise SystemExit(f"No runs table. Tables: {tables}")
for (rid,) in db.execute(f"select run_id from {t} order by rowid desc"):
    try:
        s = build_summary(db_path, rid)
        c = s.get("counts", {})
        print(f"{rid}  total={c.get('total')}  judged={c.get('judged')}  categories={len(s.get('categories', {}))}")
    except Exception as e:
        print(rid, "ERROR", e)
