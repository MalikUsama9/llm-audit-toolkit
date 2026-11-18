import sys
from audit.config import load_config
from audit.store import Store

base, after = sys.argv[1], sys.argv[2]
store = Store(load_config("configs/audit.yaml").paths.database)
cases = {c.id: c for c in store.get_cases()}
def scores(run):
    return {s.case_id: s for s in store.get_scores(run) if s.metric in ("correctness", "refusal")}
b, a = scores(base), scores(after)
rb = {r.case_id: r for r in store.get_results(base)}
ra = {r.case_id: r for r in store.get_results(after)}

for i in sorted(set(a) & set(b)):
    c = cases[i]
    if c.split is None or c.split.value != "dev":
        continue
    if b[i].value >= 1.0 and a[i].value < 1.0:
        print(f"\n### {i} | {c.category} | expected: {c.expected_behavior.value} | {b[i].value} -> {a[i].value}")
        print("Q:", c.question)
        print("REF:", c.reference_answer)
        print("BEFORE:", (rb[i].answer or "")[:350])
        print("AFTER: ", (ra[i].answer or "")[:350])
        print("JUDGE (after):", a[i].reasoning)