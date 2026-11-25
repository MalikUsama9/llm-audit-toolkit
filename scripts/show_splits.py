import json
for f in ("baseline_summary.json", "after_summary.json"):
    s = json.load(open(f, encoding="utf-8"))
    print(f, s["counts"], "overall:", s["overall"])
    for k, v in s["splits"].items():
        print("  split", k, v)
    print("  latency", s["latency"], "usage", s["usage"])
    