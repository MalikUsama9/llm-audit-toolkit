import sqlite3, sys, datetime

src = sys.argv[1]
c = sqlite3.connect("data/audit.db")
run = c.execute("SELECT target_name, config_snapshot FROM runs WHERE run_id=?", (src,)).fetchone()
if run is None:
    sys.exit(f"Unknown run: {src}")

new_id = "run_padded_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
c.execute("INSERT INTO runs (run_id, target_name, config_snapshot, created_at, notes) VALUES (?,?,?,?,?)",
          (new_id, run[0], run[1], datetime.datetime.now().isoformat(), "padded variant of " + src))

OPEN = [
    "Thank you so much for reaching out to Tidewell Home, we really appreciate your question and are happy to help.",
    "Hello, and thanks for contacting us. We understand how important it is to get a clear and helpful answer.",
    "Great question, and thank you for asking. We are glad you got in touch with our support team today.",
]
CLOSE = [
    "To summarize, the information above should answer your question. We hope this was helpful, and thank you again for your patience and for being a valued customer.",
    "We hope this clears things up. Please do not hesitate to reach out if there is anything else we can do for you, and have a wonderful day.",
    "Thank you once again for your question. We are always here to help, and we appreciate your business very much.",
]

rows = c.execute("SELECT case_id, answer, contexts, latency_ms, input_tokens, output_tokens, error "
                 "FROM results WHERE run_id=?", (src,)).fetchall()
changed = 0
for i, (cid, ans, ctx, lat, it, ot, err) in enumerate(rows):
    new = ans
    if err is None and (ans or "").strip():
        new = f"{OPEN[i % 3]}\n\n{ans.strip()}\n\n{CLOSE[i % 3]}"
        changed += 1
    c.execute("INSERT INTO results (run_id, case_id, answer, contexts, latency_ms, input_tokens, output_tokens, error) "
              "VALUES (?,?,?,?,?,?,?,?)", (new_id, cid, new, ctx, lat, it, ot, err))
c.commit()
print(f"{new_id} | cases: {len(rows)} | padded: {changed}", file=sys.stderr)
print(new_id)  # stdout: only the id, so PowerShell can capture it