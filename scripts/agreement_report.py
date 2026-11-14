"""Step 5.8: human vs judge agreement. No LLM calls."""
import sqlite3, math, csv, os
from collections import Counter

H2V = {"correct": 1.0, "partially_correct": 0.5, "partial": 0.5,
       "incorrect": 0.0, "wrong": 0.0, "hallucinated": 0.0, "fabricated": 0.0,
       "appropriate_refusal": 1.0, "wrongful_refusal": 0.0, "missed_clarification": 0.5}
NAME = {1.0: "good", 0.5: "partial", 0.0: "bad"}
ORDER = ["good", "partial", "bad"]

con = sqlite3.connect("data/audit.db")
print("Human labels used:", con.execute("SELECT label, COUNT(*) FROM human_labels GROUP BY label").fetchall())

rows = con.execute("""
    SELECT h.run_id, h.case_id, h.label, s.value, s.reasoning
    FROM human_labels h
    JOIN scores s ON s.run_id = h.run_id AND s.case_id = h.case_id
                 AND s.metric IN ('correctness', 'refusal')
    ORDER BY h.case_id""").fetchall()
print(f"Labeled cases with a judge score: {len(rows)} (human_labels has "
      f"{con.execute('SELECT COUNT(*) FROM human_labels').fetchone()[0]} rows)")

pairs, unknown = [], Counter()
for run, cid, label, val, why in rows:
    hv = H2V.get((label or "").strip().lower())
    if hv is None:
        unknown[label] += 1
        continue
    pairs.append((cid, NAME[hv], NAME.get(float(val), "bad"), label, why))
if unknown:
    print("WARNING: unmapped human labels (add them to H2V):", dict(unknown))
n = len(pairs)
if n == 0:
    raise SystemExit("Nothing to compare.")

def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h

def kappa(h, j):
    n = len(h)
    po = sum(a == b for a, b in zip(h, j)) / n
    ch, cj = Counter(h), Counter(j)
    pe = sum(ch[c] * cj[c] for c in ORDER) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)

hum = [p[1] for p in pairs]
jud = [p[2] for p in pairs]
agree = sum(a == b for a, b in zip(hum, jud))
lo, hi = wilson(agree, n)
print(f"\nOVERALL AGREEMENT (3 levels): {agree}/{n} = {agree/n:.1%}   95% CI {lo:.0%} to {hi:.0%}")
k = kappa(hum, jud)
print("Cohen's kappa:", "n/a" if k is None else round(k, 3))

h2 = [x == "good" for x in hum]
j2 = [x == "good" for x in jud]
a2 = sum(a == b for a, b in zip(h2, j2))
print(f"Agreement on good vs not-good: {a2}/{n} = {a2/n:.1%}")

print("\nConfusion matrix (rows = human, columns = judge)")
print(f"  {'':8}" + "".join(f"{c:>9}" for c in ORDER))
for r in ORDER:
    print(f"  {r:8}" + "".join(f"{sum(1 for h, j in zip(hum, jud) if h == r and j == c):>9}" for c in ORDER))

rank = {"bad": 0, "partial": 1, "good": 2}
lenient = sum(1 for h, j in zip(hum, jud) if rank[j] > rank[h])
strict = sum(1 for h, j in zip(hum, jud) if rank[j] < rank[h])
print(f"\nDisagreements: {n - agree}  | judge MORE lenient than human: {lenient} | judge MORE strict: {strict}")

os.makedirs("data/demo", exist_ok=True)
with open("data/demo/agreement_disagreements.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["case_id", "human", "judge", "human_label_raw", "judge_reasoning"])
    for cid, h, j, raw, why in pairs:
        if h != j:
            w.writerow([cid, h, j, raw, (why or "")[:300]])
print("Saved data/demo/agreement_disagreements.csv")
if n < 50:
    print(f"\nNOTE: only {n} labeled cases, so treat the percentage as approximate (see the CI).")