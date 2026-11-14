import sqlite3, sys, re, datetime

src = sys.argv[1]
c = sqlite3.connect("data/audit.db")
new_id = "run_variant_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

run = c.execute("SELECT target_name, config_snapshot, notes FROM runs WHERE run_id=?", (src,)).fetchone()
c.execute("INSERT INTO runs (run_id, target_name, config_snapshot, created_at, notes) VALUES (?,?,?,?,?)",
          (new_id, run[0], run[1], datetime.datetime.now().isoformat(), "variant of " + src))

def shorten(t):
    t = t or ""
    first = t.split("\n\n")[0].strip()
    if first and first != t.strip():
        return first
    sents = re.split(r"(?<=[.!?])\s+", t.strip())
    return " ".join(sents[:-1]) if len(sents) > 1 else t

rows = c.execute("SELECT case_id, answer, contexts, latency_ms, input_tokens, output_tokens, error FROM results WHERE run_id=?", (src,)).fetchall()
diff = 0
for cid, ans, ctx, lat, it, ot, err in rows:
    new = shorten(ans)
    diff += new != ans
    c.execute("INSERT INTO results (run_id, case_id, answer, contexts, latency_ms, input_tokens, output_tokens, error) VALUES (?,?,?,?,?,?,?,?)",
              (new_id, cid, new, ctx, lat, it, ot, err))
c.commit()
print(new_id, "| cases:", len(rows), "| different:", diff)