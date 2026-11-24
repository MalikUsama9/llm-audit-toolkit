import json
b = json.load(open("baseline_summary.json", encoding="utf-8"))
a = json.load(open("after_summary.json", encoding="utf-8"))

def line(name, x):
    return f"{name:10} {x['passed']}/{x['n']}  partial={x['partial']} failed={x['failed']}  rate={x['rate']*100:.1f}%  CI {x['ci_low']*100:.1f}-{x['ci_high']*100:.1f}%"

print("Run IDs:", b["run"]["run_id"], "|", a["run"]["run_id"])
for label, s in (("BASELINE", b), ("AFTER", a)):
    print(f"\n{label}")
    print(line("overall", s["overall"]))
    for k, v in s["splits"].items():
        print(line(k, v))
    for k, v in s["categories"].items():
        print("  ", line(k, v))

print("\n--- Same-conditions checks ---")
print("Same case count:", b["counts"]["total"] == a["counts"]["total"] == 118)
print("All judged, no errors:", b["counts"]["judged"] == a["counts"]["judged"] == 118 and b["counts"]["errors"] == a["counts"]["errors"] == 0)
print("Same judge model:", b["run"]["judge_model"] == a["run"]["judge_model"], b["run"]["judge_model"])
print("Same dev/heldout sizes:", all(b["splits"][k]["n"] == a["splits"][k]["n"] for k in ("dev", "heldout")),
      {k: v["n"] for k, v in b["splits"].items()})
print("Same calibration:", b["calibration"]["agree"], "/", b["calibration"]["n"], "=", round(b["calibration"]["agreement"] * 100, 1), "%")