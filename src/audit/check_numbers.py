import json, re

rows = [json.loads(l) for l in open("data/demo/testset.jsonl", encoding="utf-8") if l.strip()]
flagged = 0
for r in rows:
    if r.get("origin") != "generated" or r.get("expected_behavior") != "answer":
        continue
    nums = set(re.findall(r"\d+(?:[.,]\d+)?", r.get("reference_answer", "")))
    src = r.get("source_text", "")
    missing = [n for n in nums if n not in src]
    if missing:
        flagged += 1
        print(r["id"], r["category"], "- numbers not in source:", missing)
        print("  Q:", r["question"])
        print("  A:", r["reference_answer"])
print("Flagged:", flagged)