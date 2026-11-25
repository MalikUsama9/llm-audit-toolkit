# label_results.py
import sqlite3, random, textwrap

DB = "data/audit.db"
N = 40
LABELS = {"c": "correct", "p": "partially_correct", "w": "wrong", "h": "hallucinated"}

con = sqlite3.connect(DB)
con.execute("CREATE TABLE IF NOT EXISTS label_sample(pos INTEGER PRIMARY KEY, run_id, case_id)")
con.execute("""CREATE TABLE IF NOT EXISTS human_labels(
    run_id, case_id, label, note, labeled_at DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, case_id))""")

# build the sample once (round-robin over runs, prefer distinct cases)
if con.execute("SELECT COUNT(*) FROM label_sample").fetchone()[0] == 0:
    random.seed(42)
    by_run = {}
    for run_id, case_id in con.execute("SELECT run_id, case_id FROM results"):
        by_run.setdefault(run_id, []).append((run_id, case_id))
    for v in by_run.values():
        random.shuffle(v)
    picked, seen = [], set()
    while len(picked) < N and any(by_run.values()):
        for rid in list(by_run):
            while by_run[rid]:
                cand = by_run[rid].pop()
                if cand[1] not in seen:
                    picked.append(cand)
                    seen.add(cand[1])
                    break
            if len(picked) >= N:
                break
    con.executemany("INSERT INTO label_sample(pos, run_id, case_id) VALUES (?,?,?)",
                    [(i + 1, r, c) for i, (r, c) in enumerate(picked)])
    con.commit()

total = con.execute("SELECT COUNT(*) FROM label_sample").fetchone()[0]
todo = con.execute("""SELECT s.pos, s.run_id, s.case_id FROM label_sample s
    LEFT JOIN human_labels h ON h.run_id = s.run_id AND h.case_id = s.case_id
    WHERE h.label IS NULL ORDER BY s.pos""").fetchall()

def show(title, text, limit=None):
    text = (text or "").strip() or "(empty)"
    if limit and len(text) > limit:
        text = text[:limit] + " ...[truncated]"
    print(f"\n--- {title} ---")
    print(textwrap.fill(text, 100, replace_whitespace=False))

for pos, run_id, case_id in todo:
    case = con.execute("""SELECT category, question, reference_answer, expected_behavior, source_text
                          FROM cases WHERE id = ?""", (case_id,)).fetchone()
    res = con.execute("SELECT answer, contexts FROM results WHERE run_id = ? AND case_id = ?",
                      (run_id, case_id)).fetchone()
    print("\n" + "=" * 100)
    print(f"[{pos}/{total}]  run={run_id}  case={case_id}  category={case[0]}  expected_behavior={case[3]}")
    show("QUESTION", case[1])
    show("REFERENCE ANSWER", case[2])
    show("SOURCE TEXT", case[4], 1500)
    show("MODEL ANSWER", res[0])
    show("RETRIEVED CONTEXTS", res[1], 1500)

    while True:
        k = input("\n[c]orrect [p]artial [w]rong [h]allucinated | [s]kip [q]uit > ").strip().lower()
        if k in LABELS or k in ("s", "q"):
            break
    if k == "q":
        break
    if k == "s":
        continue
    note = input("note (optional, Enter to skip) > ").strip()
    con.execute("INSERT OR REPLACE INTO human_labels(run_id, case_id, label, note) VALUES (?,?,?,?)",
                (run_id, case_id, LABELS[k], note))
    con.commit()

print("\nProgress:", con.execute("SELECT label, COUNT(*) FROM human_labels GROUP BY label").fetchall())
con.close()