# scripts/make_label_sheet.py
"""Export ~40 stratified cases to labeling/label_sheet.csv for blind hand-labeling.
The sheet deliberately contains NO judge output."""
import csv, os, random, sqlite3, sys
from collections import defaultdict

DB_PATH = "audit.db"
RUN_ID = "run_baseline"          # change if your run is named differently
OUT = "labeling/label_sheet.csv"
SEED = 42
TARGET = 40

# category name -> how many to take. Names must match your cases.category values.
QUOTA = {
    "direct_factual": 6, "paraphrased": 5, "multi_hop": 4, "numeric": 6,
    "unanswerable": 6, "off_topic": 3, "adversarial": 4, "ambiguous": 3,
}

if os.path.exists(OUT):
    sys.exit(f"{OUT} already exists. Refusing to overwrite your labels. "
             f"Move or delete it yourself if you really want a new sheet.")

random.seed(SEED)
db = sqlite3.connect(DB_PATH)
rows = db.execute("""
    SELECT c.id, c.category, c.question, c.reference_answer,
           c.source_text, c.expected_behavior, r.answer
    FROM cases c JOIN results r ON r.case_id = c.id
    WHERE r.run_id = ? AND r.error IS NULL AND r.answer IS NOT NULL
""", (RUN_ID,)).fetchall()

if not rows:
    sys.exit(f"No results found for run '{RUN_ID}'. Check RUN_ID and table names.")

by_cat = defaultdict(list)
for r in rows:
    by_cat[r[1]].append(r)

print("Categories found in your data:")
for cat, items in sorted(by_cat.items()):
    print(f"  {cat}: {len(items)} cases")

missing = [c for c in QUOTA if c not in by_cat]
if missing:
    print(f"\nWARNING: these QUOTA categories don't exist in your data: {missing}")
    print("Fix the names in QUOTA to match the list above, or the sample will be topped up randomly.")

sample = []
for cat, n in QUOTA.items():
    pool = by_cat.get(cat, [])
    sample += random.sample(pool, min(n, len(pool)))

# top up to TARGET with random extras from anything not yet chosen
chosen = {r[0] for r in sample}
rest = [r for r in rows if r[0] not in chosen]
need = TARGET - len(sample)
if need > 0:
    sample += random.sample(rest, min(need, len(rest)))

random.shuffle(sample)  # hide category order

os.makedirs("labeling", exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig so Excel reads it right
    w = csv.writer(f)
    w.writerow(["case_id", "category", "question", "reference_answer",
                "source_text", "expected_behavior", "bot_answer",
                "my_label", "hallucinated_yes_no", "notes"])
    for r in sample:
        w.writerow(list(r) + ["", "", ""])

print(f"\n{len(sample)} cases written to {OUT}")