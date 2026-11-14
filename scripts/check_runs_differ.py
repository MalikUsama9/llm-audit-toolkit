import sqlite3
con = sqlite3.connect("data/audit.db")
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
for t in tables:
    cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
    if {"run_id", "case_id", "answer"} <= set(cols):
        rows = con.execute(
            f"SELECT a.case_id, a.answer, b.answer FROM {t} a JOIN {t} b "
            f"ON a.case_id=b.case_id WHERE a.run_id='prompt_v1' AND b.run_id='prompt_v2'"
        ).fetchall()
        diff = sum(1 for _, x, y in rows if (x or "").strip() != (y or "").strip())
        print(f"table={t} compared={len(rows)} different={diff}")
        for cid, x, y in rows[:2]:
            print("\nCASE", cid, "\nV1:", (x or "")[:200], "\nV2:", (y or "")[:200])
        break