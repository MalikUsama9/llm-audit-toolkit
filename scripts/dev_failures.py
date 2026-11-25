import sys
from collections import defaultdict
from audit.config import load_config
from audit.store import Store

base = sys.argv[1]
store = Store(load_config("configs/audit.yaml").paths.database)
cases = {c.id: c for c in store.get_cases()}
results = {r.case_id: r for r in store.get_results(base)}

bad = defaultdict(list)
for s in store.get_scores(base):
    c = cases.get(s.case_id)
    if c is None or c.split is None or c.split.value != "dev":
        continue                      # held-out stays unseen
    if s.metric in ("correctness", "refusal") and s.value < 1.0:
        bad[c.category].append((c, results.get(s.case_id), s))

n = sum(len(v) for v in bad.values())
with open("dev_failures.md", "w", encoding="utf-8") as f:
    f.write(f"# Dev-set failures and partials (run {base})\n\n{n} cases\n\n")
    for cat in sorted(bad):
        f.write(f"## {cat} ({len(bad[cat])})\n\n")
        for c, r, s in bad[cat]:
            f.write(f"### {c.id} | {s.metric} | score {s.value}\n")
            f.write(f"- Q: {c.question}\n- Reference: {c.reference_answer}\n")
            f.write(f"- Bot: {(r.answer if r else '')}\n- Judge: {s.reasoning}\n")
            f.write("- CAUSE: \n\n")
print(f"Wrote {n} dev cases to dev_failures.md")
for cat in sorted(bad):
    print(f"  {cat}: {len(bad[cat])}")