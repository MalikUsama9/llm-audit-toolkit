import sqlite3, sys, json
run = sys.argv[1]
c = sqlite3.connect("data/audit.db")
rows = c.execute("""
    SELECT c.id, c.source_ref, r.contexts FROM results r
    JOIN cases c ON c.id = r.case_id
    WHERE r.run_id = ? AND r.contexts IS NOT NULL LIMIT 6""", (run,)).fetchall()
for cid, ref, ctx in rows:
    print("CASE", cid, "| source_ref:", ref)
    try:
        for i, ch in enumerate(json.loads(ctx), 1):
            text = ch if isinstance(ch, str) else str(ch)
            print(f"   #{i}:", text.strip().split("\n")[0][:90])
    except Exception as e:
        print("   (could not parse contexts:", e, ")")
    print()