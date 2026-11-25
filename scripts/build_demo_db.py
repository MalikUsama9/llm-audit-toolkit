"""Copy only the baseline and after runs into a small, self-contained demo DB."""
import os
import sqlite3
import sys

SRC = "data/audit.db"
DST = "data/demo/demo.db"

keep = sys.argv[1:]
if len(keep) != 2:
    sys.exit("usage: python scripts/build_demo_db.py <baseline_run_id> <after_run_id>")

os.makedirs(os.path.dirname(DST), exist_ok=True)
if os.path.exists(DST):
    os.remove(DST)

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)
marks = ",".join("?" * len(keep))

tables = src.execute(
    "select name, sql from sqlite_master "
    "where type='table' and name not like 'sqlite_%'"
).fetchall()

for name, ddl in tables:
    if "cache" in name.lower():
        print("skip", name)
        continue
    dst.execute(ddl)
    cols = [c[1] for c in src.execute(f"pragma table_info({name})")]
    if "run_id" in cols:
        rows = src.execute(f"select * from {name} where run_id in ({marks})", keep).fetchall()
    elif name == "runs" and "id" in cols:
        rows = src.execute(f"select * from {name} where id in ({marks})", keep).fetchall()
    else:
        rows = src.execute(f"select * from {name}").fetchall()  # e.g. cases
    if rows:
        dst.executemany(
            f"insert into {name} values ({','.join('?' * len(cols))})", rows
        )
    print(f"{name}: {len(rows)} rows")

for (ddl,) in src.execute(
    "select sql from sqlite_master where type='index' and sql is not null"
):
    try:
        dst.execute(ddl)
    except sqlite3.Error:
        pass

dst.commit()
dst.execute("pragma journal_mode=delete")  # no -wal/-shm files next to it
dst.execute("vacuum")
dst.close()
print("size:", os.path.getsize(DST) // 1024, "KB")