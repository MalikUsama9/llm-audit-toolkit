# pick_fewshot.py
# python pick_fewshot.py                                  -> 3 candidates per category, latest run
# python pick_fewshot.py --category numeric_policy --n 5
# python pick_fewshot.py --run RUN_ID
import argparse
import sqlite3
import textwrap

p = argparse.ArgumentParser()
p.add_argument("--db", default="data/audit.db")
p.add_argument("--run", default=None, help="run_id (default: latest run)")
p.add_argument("--category", default=None)
p.add_argument("--n", type=int, default=3, help="candidates per category")
p.add_argument("--max-chars", type=int, default=600)
a = p.parse_args()

con = sqlite3.connect(a.db)
con.row_factory = sqlite3.Row

run_id = a.run or con.execute(
    "select run_id from runs order by created_at desc limit 1").fetchone()[0]

sql = """
select c.id, c.category, c.question, c.reference_answer, c.expected_behavior,
       c.difficulty, c.split, r.answer, r.error
from cases c
join results r on r.case_id = c.id and r.run_id = ?
where lower(coalesce(c.split, '')) != 'heldout'
"""
args = [run_id]
if a.category:
    sql += " and c.category = ?"
    args.append(a.category)
sql += " order by c.category, c.id"
rows = con.execute(sql, args).fetchall()

def show(label, text):
    text = (text or "").strip() or "(empty)"
    if len(text) > a.max_chars:
        text = text[: a.max_chars] + " ..."
    print(textwrap.fill(f"{label}: {text}", width=100, subsequent_indent="    "))

print(f"Run: {run_id}   (holdout cases are excluded)")
shown = {}
for r in rows:
    cat = r["category"]
    if shown.get(cat, 0) >= a.n:
        continue
    shown[cat] = shown.get(cat, 0) + 1
    print("\n" + "=" * 100)
    print(f"[{r['id']}]  category={cat}  difficulty={r['difficulty']}  "
          f"expected={r['expected_behavior']}  split={r['split']}")
    show("QUESTION", r["question"])
    show("REFERENCE", r["reference_answer"])
    show("BOT ANSWER", r["answer"])
    if r["error"]:
        print("ERROR:", r["error"])
