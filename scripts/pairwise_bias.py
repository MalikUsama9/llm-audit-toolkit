# scripts/pairwise_bias.py
import csv, json, re, sqlite3, sys
from collections import Counter
from pathlib import Path
from audit.config import load_config
from audit.judge import _call_llm, strip_fences
from audit.llm.client import LLMClient

if len(sys.argv) < 3:
    raise SystemExit("usage: python scripts/pairwise_bias.py RUN_A RUN_B [MAX_CASES]")
run_a, run_b = sys.argv[1], sys.argv[2]
max_cases = int(sys.argv[3]) if len(sys.argv) > 3 else 30

cfg = load_config("configs/audit.yaml")
client = LLMClient(db_path=cfg.paths.llm_cache, budget_usd=cfg.judge.budget_usd)

SYSTEM = (
    "You compare two answers to the same customer question. Judge only factual accuracy "
    "against the reference answer and source excerpt: correct numbers, conditions and policies. "
    "Length is not quality: a longer answer is NOT better because it is longer, and a shorter "
    "answer is NOT better because it is shorter. Ignore greetings, pleasantries, repetition, "
    "restating the question, extra caveats, formatting, and the order in which the answers are shown. "
    "Count only facts that are correct or incorrect. If neither answer contains a correct fact "
    "that the other lacks, and neither contains an error the other avoids, answer tie. "
    "Reply with JSON only: {\"reasoning\": \"...\", \"winner\": \"A\" | \"B\" | \"tie\"}. "
)

con = sqlite3.connect(cfg.paths.database)
con.execute("""CREATE TABLE IF NOT EXISTS pairwise_judgments(
    run_a, run_b, case_id, order_shown, slot_winner, run_winner, reasoning,
    PRIMARY KEY (run_a, run_b, case_id, order_shown))""")

pairs = con.execute("""
    SELECT c.id, c.question, c.reference_answer, c.source_text, r1.answer, r2.answer
    FROM cases c
    JOIN results r1 ON r1.case_id = c.id AND r1.run_id = ?
    JOIN results r2 ON r2.case_id = c.id AND r2.run_id = ?
    WHERE coalesce(trim(r1.answer),'') <> '' AND coalesce(trim(r2.answer),'') <> ''
      AND r1.error IS NULL AND r2.error IS NULL
      AND r1.answer <> r2.answer
    ORDER BY c.id LIMIT ?""", (run_a, run_b, max_cases)).fetchall()
print(f"{len(pairs)} case pairs ({len(pairs)*2} judge calls max)")

def ask(question, ref, src, first, second):
    user = (f"Question: {question}\nReference answer: {ref or '(none)'}\n"
            f"Source excerpt: {src or '(none)'}\n\nAnswer A: {first}\n\nAnswer B: {second}\n\n"
            "Return the JSON object now.")
    raw = _call_llm(client, cfg.judge, SYSTEM, user, False)
    m = re.search(r"\{.*\}", strip_fences(raw), re.S)
    obj = json.loads(m.group(0))
    w = str(obj.get("winner", "")).strip().upper()
    return ("tie" if w == "TIE" else w if w in ("A", "B") else None), str(obj.get("reasoning", ""))

for case_id, q, ref, src, ans_a, ans_b in pairs:
    for order in ("AB", "BA"):
        if con.execute("SELECT 1 FROM pairwise_judgments WHERE run_a=? AND run_b=? AND case_id=? AND order_shown=?",
                       (run_a, run_b, case_id, order)).fetchone():
            continue
        first, second = (ans_a, ans_b) if order == "AB" else (ans_b, ans_a)
        try:
            slot, why = ask(q, ref, src, first, second)
        except Exception as e:
            print(f"  FAILED {case_id} {order}: {e}")
            continue
        if slot is None:
            continue
        if slot == "tie":
            winner = "tie"
        elif order == "AB":
            winner = run_a if slot == "A" else run_b
        else:
            winner = run_b if slot == "A" else run_a
        con.execute("INSERT OR REPLACE INTO pairwise_judgments VALUES (?,?,?,?,?,?,?)",
                    (run_a, run_b, case_id, order, slot, winner, why))
        con.commit()
        print(f"  {case_id:10} {order} -> slot {slot:3} -> {winner}")

# ---- analysis ----
rows = con.execute("SELECT case_id, order_shown, slot_winner, run_winner FROM pairwise_judgments "
                   "WHERE run_a=? AND run_b=?", (run_a, run_b)).fetchall()
by_case = {}
for cid, order, slot, win in rows:
    by_case.setdefault(cid, {})[order] = (slot, win)
both = {c: v for c, v in by_case.items() if len(v) == 2}
n = len(both)
if n == 0:
    raise SystemExit("No case has both orders judged.")

consistent = {c: v for c, v in both.items() if v["AB"][1] == v["BA"][1]}
flipped = {c: v for c, v in both.items() if v["AB"][1] != v["BA"][1]}
print(f"\nCases judged in both orders: {n}")
print(f"Consistent (kept):           {len(consistent)} = {100*len(consistent)/n:.1f}%")
print(f"Inconsistent (dropped):      {len(flipped)} = {100*len(flipped)/n:.1f}%  <- position bias rate")

slots = Counter(s for v in both.values() for s, _ in v.values())
print(f"Slot picked across all {2*n} verdicts: {dict(slots)}")
print("When the verdict flipped, slot picked:",
      dict(Counter(s for v in flipped.values() for s, _ in v.values() if s != "tie")))

kept = Counter(v["AB"][1] for v in consistent.values())
print(f"\nKept verdicts: {run_a}={kept.get(run_a,0)}  {run_b}={kept.get(run_b,0)}  tie={kept.get('tie',0)}")

Path("data/demo").mkdir(parents=True, exist_ok=True)
with open("data/demo/pairwise_consistent.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["case_id", "winner", "consistent"])
    for c, v in both.items():
        w.writerow([c, v["AB"][1] if c in consistent else "", c in consistent])
print("Saved data/demo/pairwise_consistent.csv")