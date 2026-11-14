# scripts/agreement.py
import re, sqlite3, csv
from collections import Counter
from pathlib import Path

DB = "data/audit.db"
H = {"correct": "pass", "partially_correct": "partial", "wrong": "fail", "hallucinated": "fail"}
J = {"correct": "pass", "appropriate_refusal": "pass", "partially_correct": "partial",
     "incorrect": "fail", "wrongful_refusal": "fail", "fabricated": "fail",
     "missed_clarification": "partial"}
LV = ["pass", "partial", "fail"]

con = sqlite3.connect(DB)
rows = con.execute("""
    SELECT h.run_id, h.case_id, h.label, h.note, c.category, c.expected_behavior,
           s.metric, s.reasoning
    FROM human_labels h
    JOIN cases c  ON c.id = h.case_id
    JOIN scores s ON s.run_id = h.run_id AND s.case_id = h.case_id
                  AND s.metric IN ('correctness','refusal')""").fetchall()

data = []
for run_id, case_id, label, note, cat, beh, metric, reasoning in rows:
    m = re.match(r"\[(\w+)\]", reasoning or "")
    if not m or m.group(1) not in J:
        continue
    jv = m.group(1)
    data.append(dict(run=run_id, case=case_id, h_label=label, h=H[label], j_verdict=jv, j=J[jv],
                     cat=cat, beh=beh, note=note or ""))

n = len(data)
if n == 0:
    raise SystemExit("No judged + labeled pairs found. Run run_judge_on_labels.py first.")

def pct(a, b): return f"{100*a/b:.1f}%" if b else "n/a"
agree = sum(d["h"] == d["j"] for d in data)

print(f"Compared {n} items\n")
print(f"3-way agreement (pass/partial/fail): {agree}/{n} = {pct(agree, n)}")
bin_agree = sum((d["h"] == "pass") == (d["j"] == "pass") for d in data)
print(f"Binary agreement (pass vs not pass): {bin_agree}/{n} = {pct(bin_agree, n)}")

maj = Counter(d["h"] for d in data).most_common(1)[0]
print(f"Baseline (always say '{maj[0]}'):      {maj[1]}/{n} = {pct(maj[1], n)}")

# Cohen's kappa
po = agree / n
ch, cj = Counter(d["h"] for d in data), Counter(d["j"] for d in data)
pe = sum((ch[l] / n) * (cj[l] / n) for l in LV)
kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
print(f"Cohen's kappa (3-way): {kappa:.2f}   (0.6+ decent, 0.8+ strong)")

print("\nBy case type:")
for name, sel in [("answer cases", lambda d: d["beh"] == "answer"),
                  ("refuse/handoff/clarify", lambda d: d["beh"] != "answer")]:
    sub = [d for d in data if sel(d)]
    a = sum(d["h"] == d["j"] for d in sub)
    print(f"  {name:24} {a}/{len(sub)} = {pct(a, len(sub))}")

print("\nBy your label (how often the judge agrees with you):")
for lab in ["correct", "partially_correct", "wrong", "hallucinated"]:
    sub = [d for d in data if d["h_label"] == lab]
    a = sum(d["h"] == d["j"] for d in sub)
    print(f"  {lab:18} {a}/{len(sub)} = {pct(a, len(sub))}")

print("\nConfusion matrix (rows = you, columns = judge):")
print(f"{'':10}" + "".join(f"{l:>9}" for l in LV))
for hl in LV:
    print(f"{hl:10}" + "".join(f"{sum(d['h']==hl and d['j']==jl for d in data):>9}" for jl in LV))

dis = [d for d in data if d["h"] != d["j"]]
print(f"\nDisagreements: {len(dis)}")
for d in dis:
    print(f"  {d['case']:10} you={d['h_label']:18} judge={d['j_verdict']:20} [{d['beh']}] {d['note'][:70]}")

Path("data/demo").mkdir(parents=True, exist_ok=True)
with open("data/demo/disagreements.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
    w.writeheader()
    w.writerows(dis)
print("\nSaved data/demo/disagreements.csv")