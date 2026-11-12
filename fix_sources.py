import json, shutil, sqlite3

FIX = {
    "gen-098": ("data/demo/docs/04_pricing_payments_promotions.md", "clearly wrong price"),
    "human-02": ("data/demo/docs/10_warranty.md", "if we need the item back"),
}

def find_line(path, key):
    for l in open(path, encoding="utf-8"):
        if key in l:
            return l.strip()
    raise SystemExit(f"text not found in {path}")

extra = {cid: find_line(p, k) for cid, (p, k) in FIX.items()}

shutil.copy("data/demo/testset.jsonl", "data/demo/testset_before_source_fix.jsonl")
shutil.copy("data/audit.db", "data/audit_before_source_fix.db")

rows = [json.loads(l) for l in open("data/demo/testset.jsonl", encoding="utf-8") if l.strip()]
for r in rows:
    if r["id"] in extra and extra[r["id"]] not in (r.get("source_text") or ""):
        r["source_text"] = (r.get("source_text") or "") + "\n\n" + extra[r["id"]]
        print("testset updated:", r["id"])
with open("data/demo/testset.jsonl", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

con = sqlite3.connect("data/audit.db")
for cid, line in extra.items():
    cur = con.execute("SELECT source_text FROM cases WHERE id=?", (cid,)).fetchone()
    if cur and line not in (cur[0] or ""):
        con.execute("UPDATE cases SET source_text=? WHERE id=?", ((cur[0] or "") + "\n\n" + line, cid))
        print("db updated:", cid)
con.commit()
