# validate_rubrics.py  -> python validate_rubrics.py
import sys, yaml, pathlib

DIR = pathlib.Path("configs/rubrics")
EXPECTED = {
    "correctness": {"correct", "partially_correct", "incorrect"},
    "faithfulness": {"supported", "contradicted", "not_in_source"},
    "refusal": {"appropriate_refusal", "fabricated", "wrongful_refusal"},
}
errors, total_shots, ids = [], 0, []

for name, labels in EXPECTED.items():
    path = DIR / f"{name}.yaml"
    if not path.exists():
        errors.append(f"{name}: file missing"); continue
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not d.get("version"):
        errors.append(f"{name}: no version")
    got = set((d.get("labels") or {}).keys())
    if got != labels:
        errors.append(f"{name}: labels {sorted(got)} != {sorted(labels)}")
    for lab, body in (d.get("labels") or {}).items():
        if not body.get("definition") or not body.get("borderline"):
            errors.append(f"{name}.{lab}: needs definition AND borderline")
    rules = " ".join(d.get("rules") or []).lower()
    if "length is not quality" not in rules:
        errors.append(f"{name}: missing 'length is not quality'")
    if "material claims only" not in rules:
        errors.append(f"{name}: missing 'material claims only'")
    for shot in d.get("few_shot") or []:
        total_shots += 1
        ids.append(str(shot.get("case_id")))
        if "REPLACE" in str(shot):
            errors.append(f"{name}: few-shot {shot.get('case_id')} still has REPLACE text")
        if shot.get("verdict") not in labels and name != "faithfulness":
            errors.append(f"{name}: few-shot {shot.get('case_id')} bad verdict")

if not 4 <= total_shots <= 6:
    errors.append(f"few-shot total is {total_shots}, need 4 to 6")
if len(ids) != len(set(ids)):
    errors.append("a case ID is used in more than one few-shot example")

if errors:
    print("PROBLEMS:"); [print(" -", e) for e in errors]; sys.exit(1)

(DIR / "few_shot_ids.txt").write_text("\n".join(sorted(ids)) + "\n", encoding="utf-8")
print(f"OK: 3 rubrics valid, {total_shots} few-shot examples.")
print("Wrote configs/rubrics/few_shot_ids.txt (exclude these IDs from calibration on Day 5).")